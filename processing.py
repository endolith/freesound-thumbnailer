#!/usr/bin/env python

# processing.py -- various audio processing functions
# Copyright (C) 2008 MUSIC TECHNOLOGY GROUP (MTG)
#                    UNIVERSITAT POMPEU FABRA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#   Bram de Jong <bram.dejong at domain.com where domain in gmail>

from PIL import ImageFilter, ImageChops, Image, ImageDraw, ImageColor
from functools import partial
from time import time
import math
import numpy
import os
import re
import scikits.audiolab as audiolab
import subprocess
import sys

class AudioProcessingException(Exception):
    pass

class TestAudioFile(object):
    """A class that mimics audiolab.sndfile but generates noise instead of reading
    a wave file. Additionally it can be told to have a "broken" header and thus crashing
    in the middle of the file. Also useful for testing ultra-short files of 20 samples."""
    def __init__(self, num_frames, has_broken_header=False):
        self.seekpoint = 0
        self.nframes = num_frames
        self.samplerate = 44100
        self.channels = 1
        self.has_broken_header = has_broken_header

    def seek(self, seekpoint):
        self.seekpoint = seekpoint

    def read_frames(self, frames_to_read):
        if self.has_broken_header and self.seekpoint + frames_to_read > self.num_frames / 2:
            raise RuntimeError()

        num_frames_left = self.num_frames - self.seekpoint
        will_read = num_frames_left if num_frames_left < frames_to_read else frames_to_read
        self.seekpoint += will_read
        return numpy.random.random(will_read)*2 - 1 


def get_max_level(filename):
    max_value = 0
    buffer_size = 4096
    audio_file = audiolab.Sndfile(filename, 'r')
    n_samples_left = audio_file.nframes

    while n_samples_left:
        to_read = min(buffer_size, n_samples_left)

        try:
            samples = audio_file.read_frames(to_read)
        except RuntimeError:
            # this can happen with a broken header
            break

        # convert to mono by selecting left channel only
        if audio_file.channels > 1:
            samples = samples[:,0]

        max_value = max(max_value, numpy.abs(samples).max())

        n_samples_left -= to_read

    audio_file.close()

    return max_value

class AudioProcessor(object):
    """
    The audio processor processes chunks of audio and calculates the spectral centroid and the peak
    samples in that chunk of audio.
    """
    def __init__(self, input_filename, fft_size, window_function=numpy.hanning):
        max_level = get_max_level(input_filename)

        self.audio_file = audiolab.Sndfile(input_filename, 'r')
        self.fft_size = fft_size
        self.window = window_function(self.fft_size)
        self.spectrum_range = None
        self.lower = 100
        self.higher = 22050
        self.lower_log = math.log10(self.lower)
        self.higher_log = math.log10(self.higher)
        self.clip = lambda val, low, high: min(high, max(low, val))

        # figure out what the maximum value is for an FFT doing the FFT of a DC signal
        fft = numpy.fft.rfft(numpy.ones(fft_size) * self.window)
        max_fft = (numpy.abs(fft)).max()
        # set the scale to normalized audio and normalized FFT
        self.scale = 1.0/max_level/max_fft if max_level > 0 else 1

    def read(self, start, size, resize_if_less=False):
        """ read size samples starting at start, if resize_if_less is True and less than size
        samples are read, resize the array to size and fill with zeros """
        
        # number of zeros to add to start and end of the buffer
        add_to_start = 0
        add_to_end = 0

        if start < 0:
            if size + start <= 0:
                return numpy.zeros(size) if resize_if_less else numpy.array([])
            self.audio_file.seek(0)

            add_to_start = -start # remember: start is negative!
            to_read = size + start

            if to_read > self.audio_file.nframes:
                add_to_end = to_read - self.audio_file.nframes
                to_read = self.audio_file.nframes
        else:
            self.audio_file.seek(start)

            to_read = size
            if start + to_read >= self.audio_file.nframes:
                to_read = self.audio_file.nframes - start
                add_to_end = size - to_read

        try:
            samples = self.audio_file.read_frames(to_read)
        except RuntimeError:
            # this can happen for wave files with broken headers...
            return numpy.zeros(size) if resize_if_less else numpy.zeros(2)

        # convert to mono by selecting left channel only
        if self.audio_file.channels > 1:
            samples = samples[:,0]

        if resize_if_less and (add_to_start > 0 or add_to_end > 0):
            if add_to_start > 0:
                samples = numpy.concatenate((numpy.zeros(add_to_start), samples), axis=1)

            if add_to_end > 0:
                samples = numpy.resize(samples, size)
                samples[size - add_to_end:] = 0

        return samples


    def spectral_centroid(self, seek_point, spec_range=110.0):
        """ starting at seek_point read fft_size samples, and calculate the spectral centroid """
        
        samples = self.read(seek_point - self.fft_size/2, self.fft_size, True)

        samples *= self.window
        fft = numpy.fft.rfft(samples)
        spectrum = self.scale * numpy.abs(fft) # normalized abs(FFT) between 0 and 1
        length = numpy.float64(spectrum.shape[0])
        spectrum[:2] = 0 # DC offset should not be included

        energy = spectrum.sum()
        if energy < 1e-60:
            spectral_centroid = -1 # Silence
        else:
            # calculate the spectral centroid

            if self.spectrum_range is None:  #Always is?
                self.spectrum_range = numpy.arange(length)

            # Compute the spectral centroid in hertz
            spectral_centroid = (spectrum * self.spectrum_range).sum() / (energy * (length - 1)) * self.audio_file.samplerate * 0.5

            # Clip centroid to desired frequency range, apply log so it's 
            # proportional to human perception of frequency, and then scale 
            # desired frequency range from 0 to 1
            spectral_centroid = (math.log10(self.clip(spectral_centroid, self.lower, self.higher)) - self.lower_log) / (self.higher_log - self.lower_log)

        return (spectral_centroid)


    def peaks(self, start_seek, end_seek):
        """ read all samples between start_seek and end_seek, then find the minimum and maximum peak
        in that range. Returns that pair in the order they were found. So if min was found first,
        it returns (min, max) else the other way around. """
        
        # larger blocksizes are faster but take more mem...
        # Aha, Watson, a clue, a tradeof!
        block_size = 4096

        max_index = -1
        max_value = -1
        min_index = -1
        min_value = 1

        if end_seek > self.audio_file.nframes:
            end_seek = self.audio_file.nframes

        block_size = min(block_size, end_seek - start_seek)
        for i in range(start_seek, end_seek, block_size):
            samples = self.read(i, block_size)

            local_max_index = numpy.argmax(samples)
            local_max_value = samples[local_max_index]

            if local_max_value > max_value:
                max_value = local_max_value
                max_index = local_max_index

            local_min_index = numpy.argmin(samples)
            local_min_value = samples[local_min_index]

            if local_min_value < min_value:
                min_value = local_min_value
                min_index = local_min_index

        return (min_value, max_value) if min_index < max_index else (max_value, min_value)


def interpolate_colors(colors, flat=False, num_colors=256):
    """ given a list of colors, create a larger list of colors linearly interpolating
    the first one. If flatten is True a list of numbers will be returned. If
    False, a list of (r,g,b) tuples. num_colors is the number of colors wanted
    in the final list """
    
    palette = []
    
    for i in range(num_colors):
        index = (i * (len(colors) - 1))/(num_colors - 1.0) # same as numpy.linspace(0,len(colors)-1,num_colors)
        index_int = int(index)
        alpha = index - float(index_int)
        
        if alpha > 0:
            r = (1.0 - alpha) * colors[index_int][0] + alpha * colors[index_int + 1][0]
            g = (1.0 - alpha) * colors[index_int][1] + alpha * colors[index_int + 1][1]
            b = (1.0 - alpha) * colors[index_int][2] + alpha * colors[index_int + 1][2]
        else:
            r = (1.0 - alpha) * colors[index_int][0]
            g = (1.0 - alpha) * colors[index_int][1]
            b = (1.0 - alpha) * colors[index_int][2]
        
        if flat:
            palette.extend((int(r), int(g), int(b)))
        else:
            palette.append((int(r), int(g), int(b)))
        
    return palette


def desaturate(rgb, amount):
    """
        desaturate colors by amount
        amount == 0, no change
        amount == 1, grey
    """
    luminosity = sum(rgb) / 3.0
    desat = lambda color: color - amount * (color - luminosity)

    return tuple(map(int, map(desat, rgb)))


class WaveformImage(object):
    """
    Given peaks and spectral centroids from the AudioProcessor, this class will construct
    a wavefile image which can be saved as PNG.
    """
    def __init__(self, image_width, image_height, palette=1):
        if image_height % 2 == 0:
            raise AudioProcessingException, "Height should be an odd number: images look much better this way"

        if palette == 1:
            background_color = (0,0,0)
            colors = [
                        (50,0,200),
                        (0,220,80),
                        (255,224,0),
                        (255,70,0),
                     ]
        elif palette == 2:
            background_color = (0,0,0)
            colors = [self.color_from_value(value/29.0) for value in range(0,30)]
        elif palette == 3:
            background_color = (213, 217, 221)
            colors = map( partial(desaturate, amount=0.7), [
                        (50,0,200),
                        (0,220,80),
                        (255,224,0),
                     ])
        elif palette == 4:
             background_color = (213, 217, 221)
             colors = map( partial(desaturate, amount=0.8), [self.color_from_value(value/29.0) for value in range(0,30)])
            
        self.image = Image.new("RGB", (image_width, image_height), background_color)
        
        self.image_width = image_width
        self.image_height = image_height
        
        self.draw = ImageDraw.Draw(self.image)
        self.previous_x, self.previous_y = None, None
        
        self.color_lookup = interpolate_colors(colors)
        self.pix = self.image.load()

    def color_from_value(self, value):
        """ given a value between 0 and 1, return an (r,g,b) tuple """

        return ImageColor.getrgb("hsl(%d,%d%%,%d%%)" % (int( (1.0 - value) * 360 ), 80, 50))
        
    def draw_peaks(self, x, peaks, spectral_centroid):
        """ draw 2 peaks at x using the spectral_centroid for color """

        y1 = self.image_height * 0.5 - peaks[0] * (self.image_height - 4) * 0.5
        y2 = self.image_height * 0.5 - peaks[1] * (self.image_height - 4) * 0.5

        if spectral_centroid == -1:
            # Dark gray for silence
            line_color = (50, 50, 50)
        else:
            line_color = self.color_lookup[int(spectral_centroid*255.0)]

        if self.previous_y is None:
            self.draw.line([x, y1, x, y2], line_color)

        else:
            self.draw.line([self.previous_x, self.previous_y, x, y1, x, y2], line_color)
        self.previous_x, self.previous_y = x, y2

        self.draw_anti_aliased_pixels(x, y1, y2, line_color)
    
    def draw_anti_aliased_pixels(self, x, y1, y2, color):
        """ vertical anti-aliasing at y1 and y2 """

        y_max = max(y1, y2)
        y_max_int = int(y_max)
        alpha = y_max - y_max_int

        if alpha > 0.0 and alpha < 1.0 and y_max_int + 1 < self.image_height:
            current_pix = self.pix[x, y_max_int + 1]

            r = int((1-alpha)*current_pix[0] + alpha*color[0])
            g = int((1-alpha)*current_pix[1] + alpha*color[1])
            b = int((1-alpha)*current_pix[2] + alpha*color[2])

            self.pix[x, y_max_int + 1] = (r,g,b)

        y_min = min(y1, y2)
        y_min_int = int(y_min)
        alpha = 1.0 - (y_min - y_min_int)

        if alpha > 0.0 and alpha < 1.0 and y_min_int >= 1:
            current_pix = self.pix[x, y_min_int - 1]

            r = int((1-alpha)*current_pix[0] + alpha*color[0])
            g = int((1-alpha)*current_pix[1] + alpha*color[1])
            b = int((1-alpha)*current_pix[2] + alpha*color[2])

            self.pix[x, y_min_int - 1] = (r,g,b)
            
    def save(self, filename):
        # draw a zero "zero" line
        a = 25
        for x in range(self.image_width):
            self.pix[x, self.image_height/2] = tuple(map(lambda p: p+a, self.pix[x, self.image_height/2]))
        
        self.image.save(filename, format = 'png')
        

def create_wave_images(input_filename, output_filename_w, output_filename_s, image_width, image_height, fft_size, progress_callback=None):
    """
    Utility function for creating both wavefile and spectrum images from an audio input file.
    """
    start_time = time()
    processor = AudioProcessor(input_filename, fft_size, numpy.hanning)
    samples_per_pixel = processor.audio_file.nframes / float(image_width)

    waveform = WaveformImage(image_width, image_height)

    for x in range(image_width):
        if time() - start_time > 30: # Kludge to crash if it takes longer than 10 seconds
            raise Exception("Took too long")
        if progress_callback and x % (image_width/10) == 0:
            progress_callback((x*100)/image_width)

        seek_point = int(x * samples_per_pixel)
        next_seek_point = int((x + 1) * samples_per_pixel)

        spectral_centroid = processor.spectral_centroid(seek_point)
        peaks = processor.peaks(seek_point, next_seek_point)

        waveform.draw_peaks(x, peaks, spectral_centroid)

    if progress_callback:
        progress_callback(100)

    waveform.save(output_filename_w)


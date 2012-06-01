A script to generate thumbnails for audio files, derived from the method used on Freesound.org

Dependencies:
 * NumPy
 * PIL (Python Imaging Library)
 * scikits "audiolab" (use setuptools' easy_install, for instance)
    * dependency: libsndfile
    
Then to set this as your thumbnailer, run gconf-editor, go to /desktop/gnome/thumbnailers/, and, for each file format you want to be thumbnailed, edit the "command" key and change the line to something like this:

    /[path to]/wav2png.py -w %s %i -a %o
    
(In Ubuntu, it defaults to `/usr/bin/totem-video-thumbnailer -s %s %u %o`, which, as far as I know, does nothing.)

Then check the "enable" checkbox, and when you refresh a folder with audio files in it, it should show the thumbnails.

Error messages for Gnome thumbnailers end up in the file `~/.xsession-errors`, intuitively enough.  >:(

You can create new entries with commands like this:

    gconftool-2 --type=bool --set "/desktop/gnome/thumbnailers/audio@x-aiff/enable" "true"

I don't know how else to add a new filetype.  Then just edit it in gconf-editor to match the other filetypes.

Bugs/Todo:
 - On short files it fails - "step argument must not be zero"
 - Fails on GSM WAV - can't seek
 - Locks up the CPU on 32-bit float - audiolab reads it incorrectly? - implement a better timeout?
 - Should it plot both channels of a stereo file?  Should it mix them?  Should it show 4-channel files as 4 skinnier tracks in a square?
 - Discontinuity at beginning affects color.  Fade in and out?
 - Blend colors like the real light spectrum so that white noise is white?  Most things just end up greenish yellow.  Planning to experiment with other methods anyway...
 - Put some kind of border around it like movie thumbnails to show that it's a sound file? 
 - I've switched from Ubuntu to Windows 7 and I'd love to be able to see these in Windows, but writing a thumbnailer seems more involved. Someone do it for me, plz!  :/  http://superuser.com/q/267392/13889
 - Make it faster?  Rewrite from scratch?

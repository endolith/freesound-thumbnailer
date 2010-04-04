A script to generate thumbnails for audio files, derived from the method used on Freesound.org

Dependencies:
 * NumPy
 * PIL (Python Imaging Library)
 * scikits "audiolab" (use setuptools' easy_install, for instance)
    * dependency: libsndfile
    
Then to set this as your thumbnailer, run gconf-editor, go to /desktop/gnome/thumbnailers/, and, for each file format you want to be thumbnailed, edit the "command" key and change the line to something like this:

    /[path to]/wav2png.py -w %s %i -a %o
    
(In Ubuntu, it defaults to "/usr/bin/totem-video-thumbnailer -s %s %u %o", which, as far as I know, does nothing.)

Then check the "enable" checkbox, and when you refresh a folder with audio files in it, it should show the thumbnails.


HTK includes versatile tools for feature extraction, model training, and recognition. The versatility, however, makes the process of training a model fairly involved. This project includes code written in Python that takes as input a list of audio files and their transcriptions, and automatically trains a model. Code for recognition is included as well. The goal is to make it as easy as possible to train a Large Vocabulary Continuous Speech Recognition (LVCSR) system.

Requires:
  * Python 2.5+ (http://www.python.org/download/)
  * HTK 3.4 (http://htk.eng.cam.ac.uk/download.shtml)
  * SRILM (http://www.speech.sri.com/projects/srilm/download.html)
  * sph2pipe (http://www.ldc.upenn.edu/Using/) for audio processing with LDC data
  * A pronunciation dictionary (https://cmusphinx.svn.sourceforge.net/svnroot/cmusphinx/trunk/cmudict/cmudict.0.7a)
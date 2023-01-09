# CHIP-8

This is a working CHIP-8 emulator/interpreter written in Python.

Opcode descriptions sourced from [Cowgod's CHIP-8 Technical Reference](http://devernay.free.fr/hacks/chip8/C8TECH10.HTM#2.2).  Note that this document has two known "errors."  The original Fx55 and Fx65 incremented I.  However, this is not needed in modern architectures and was not included in this guide, so most modern emulators do not increment I.  Similarly, The original 8xy6 and 8xyE copied Vy into Vx and then shifted.  However, this document says that Vx is shifted and Vy is ignored.  There are configuration options that need to be set depending on whether a modern or an original ROM is being executed. 

Will play any CHIP-8 ROM that works on the classic/original.  A test ROM may be found at https://github.com/Timendus/chip8-test-suite/

## To use

To run the emulator, you need to install pygame.  With Python 3.10 or earlier, ```pip install pygame``` works fine.  However, as of this writing there is no wheel for pygame with Python 3.11 or later (see: https://github.com/pygame/pygame/issues/3307).  So you can install with ```pip install pygame --pre```.

Once completed, modify the code to load the ROM you would like and then ```python3 chip8.py``` (Or ```python chip8.py``` if you're in Windows).  Reason for modifying the code is that each ROM needs to have the delay settings tweaked to get the speed appropriate for the given system.

CHIP-8 devices had a 16-character keypad laid out as follows:

```
1 2 3 C
4 5 6 D
7 8 9 E
A 0 B F
```

These are mapped to the following keys in this emulator:

```
1 2 3 4
Q W E R
A S D F
Z X C V
```

The test ROM listed above used the E/F keys to move up and down and the A key to select a test.  So on this system, use F/V to move up and down and Z to select a test.


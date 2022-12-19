import pygame
from array import array

SCALE_FACTOR = 16


def build_pygame_sound_samples():
    # modified from: https://gist.github.com/ohsqueezy/6540433
    period = int(round(pygame.mixer.get_init()[0] / 440))
    samples = array("h", [0] * period)
    amplitude = 2 ** (abs(pygame.mixer.get_init()[1]) - 1) - 1
    for time in range(period):
        if time < period / 2:
            samples[time] = amplitude
        else:
            samples[time] = -amplitude
    return samples


class C8Computer:

    def __init__(self):
        # 4096 Bytes of RAM
        self.RAM = array('B', [0 for i in range(4096)])
        # The 16 registers are named V0..VF
        self.V = array('B', [0 for i in range(16)])
        # Special-purpose 16-bit register; low 12 are used for an address
        self.I = 0
        self.delay_register = 0
        self.sound_register = 0
        # Program Counter
        self.PC = 0x200
        # One could use RAM for the stack and use a stack pointer but this is easier
        self.stack = []
        self.load_font_sprites()

    def debug_dump(self):
        outfile = open("debug.txt", "w")
        outfile.write("PC: {}\n".format(self.PC))
        outfile.write("I: {}\n".format(self.I))
        for i in range(16):
            outfile.write("V{}: {}".format(hex(i).upper()[2], self.V[i]))
            if i % 4 == 3:
                outfile.write('\n')
            else:
                outfile.write('\t')
        outfile.write("delay register: {}\n".format(self.delay_register))
        outfile.write("sound register: {}\n".format(self.sound_register))
        outfile.write("PC: {}\n".format(self.PC))
        outfile.write("stack: {}\n".format(self.stack))
        outfile.write("\n\nRAM:\n")
        for i in range(4096):
            if i % 32 == 0:
                outfile.write("0x{} - 0x{}:  ".format(hex(i)[2:].zfill(3).upper(), hex(i+63)[2:].zfill(3).upper()))
            outfile.write(hex(self.RAM[i])[2:].zfill(2).upper())
            if i % 32 == 31:
                outfile.write("\n")

        outfile.close()

    def load_font_sprites(self):
        '''
        Video in the CHIP-8 is sprite-driven.  Each sprite is 8 pixels wide, and from 1-15 pixels high.
        A font representing 0..9 + A..F is required for proper operation.  Example for the character 2:

                   *****
                   ....*
                   *****
                   *....
                   *****

        The font has to live in RAM in range 0x000-0xFFF, which is reserved for the interpreter.  Since
        we are not using any of that RAM for our actual interpreter, we will put the font starting at
        0x000.
        '''

        font = [0xF, 0x9, 0x9, 0x9, 0xF, #0
                0x2, 0x6, 0x2, 0x2, 0x7, #1
                0xF, 0x1, 0xF, 0x8, 0xF, #2
                0xF, 0x1, 0xF, 0x1, 0xF, #3
                0x9, 0x9, 0xF, 0x1, 0x1, #4
                0xF, 0x8, 0xF, 0x1, 0xF, #5
                0xF, 0x8, 0xF, 0x9, 0xF, #6
                0xF, 0x1, 0x2, 0x4, 0x4, #7
                0xF, 0x9, 0xF, 0x9, 0xF, #8
                0xF, 0x9, 0xF, 0x1, 0xF, #9
                0xF, 0x9, 0xF, 0x9, 0x9, #A
                0xE, 0x9, 0xE, 0x9, 0xE, #B
                0xF, 0x8, 0x8, 0x8, 0xF, #C
                0xE, 0x9, 0x9, 0x9, 0xE, #D
                0xF, 0x8, 0xF, 0x8, 0xF, #E
                0xF, 0x8, 0xF, 0x8, 0x8] #F
        for i in range(80):
            self.RAM[i] = font[i]

    def load_rom(self, rom_file="IBMLogo.ch8"):
        i = 0x200
        infile = open(rom_file, "rb")
        done = False
        while not done:
            nextbyte = infile.read(1)
            if not nextbyte:
                done = True
            else:
                self.RAM[i] = int.from_bytes(nextbyte, 'big')
                i += 1

class C8Screen:
    def __init__(self):
        self.vram = [[0 for i in range(64)] for j in range(32)]

    def setpx(self, x, y, val):
        assert val in (0, 1)
        assert 0 <= x <= 63
        assert 0 <= y <= 31
        self.vram[y][x] = val

    def draw(self, window):
        for x in range(64):
            for y in range(32):
                startx = x*SCALE_FACTOR
                starty = y*SCALE_FACTOR
                if self.vram[y][x] == 0:
                    color = (0,0,0)
                else:
                    color = (255,255,255)
                # print('render (' + str(x) + ',' + str(y) + ') as ' + str(self.vram[y][x]))
                for i in range(SCALE_FACTOR):
                    for j in range(SCALE_FACTOR):
                        window.set_at((startx + i, starty + j), color)

def main():

    c8 = C8Computer()
    c8.load_rom("IBMLogo.ch8")
    c8.debug_dump()
    '''
    pygame.mixer.pre_init(44100, -16, 1, 1024)
    pygame.init()
    window = pygame.display.set_mode((64 * SCALE_FACTOR, 32 * SCALE_FACTOR))
    pygame.display.set_caption("Fred's CHIP-8 Emulator")
    window.fill(0)

    beep = pygame.mixer.Sound(build_pygame_sound_samples())
    beep.set_volume(0.1)

    run = True
    myscreen = C8Screen()
    px = 0
    py = 0

    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                # pos = pygame.mouse.get_pos()
                # window.set_at(pos, white)
                myscreen.setpx(px,py,1)
                myscreen.draw(window)
                px += 1
                if px % 2 == 0:
                    py += 1
            elif event.type == pygame.KEYDOWN:
                beep.play(-1)
            elif event.type == pygame.KEYUP:
                beep.stop()
        pygame.display.flip()

    pygame.midi.quit()
    '''


if __name__ == "__main__":
    # call the main function
    main()
    pygame.quit()

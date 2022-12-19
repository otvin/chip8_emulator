import pygame
from array import array
from time import sleep

SCALE_FACTOR = 16
DISPLAY_CYCLES = 0
PIXEL_OFF = (0, 0, 0)
PIXEL_ON = (255, 255, 255)

class InvalidOpCodeException(Exception):
    pass


class OpCodeNotImplementedException(Exception):
    pass


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
        outfile.write("PC: 0x{}\n".format(hex(self.PC).upper()[2:]))
        outfile.write("I: 0x{}\n".format(hex(self.I).upper()[2:]))
        for i in range(16):
            outfile.write("V{}: 0x{}".format(hex(i).upper()[2], hex(self.V[i])[2:].zfill(2).upper()))
            if i % 4 == 3:
                outfile.write('\n')
            else:
                outfile.write('\t')
        outfile.write("delay register: {}\n".format(self.delay_register))
        outfile.write("sound register: {}\n".format(self.sound_register))
        outfile.write("stack: {}\n".format(self.stack))
        outfile.write("\n\nRAM:\n")
        for i in range(4096):
            if i % 32 == 0:
                outfile.write("0x{} - 0x{}:  ".format(hex(i)[2:].zfill(3).upper(), hex(i+31)[2:].zfill(3).upper()))
            outfile.write(hex(self.RAM[i])[2:].zfill(2).upper())
            if i % 32 == 31:
                outfile.write("\n")

        outfile.close()

    def load_font_sprites(self):
        '''
        Video in the CHIP-8 is sprite-driven.  Each sprite is 8 pixels wide, and from 1-15 pixels high.
        A font representing 0..9 + A..F is required for proper operation.  Example for the character 2:

                   ****....
                   ...*....
                   ****....
                   *.......
                   ****....

        The font has to live in RAM in range 0x000-0xFFF, which is reserved for the interpreter.  Since
        we are not using any of that RAM for our actual interpreter, we will put the font starting at
        0x000.
        '''

        font = [0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
                0x20, 0x60, 0x20, 0x20, 0x70,  # 1
                0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
                0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
                0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
                0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
                0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
                0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
                0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
                0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
                0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
                0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
                0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
                0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
                0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
                0xF0, 0x80, 0xF0, 0x80, 0x80]  # F
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

    def fetch(self):
        # All instructions start on even memory addresses
        assert (self.PC % 2 == 0)
        # Cannot exceed RAM boundary for programs
        assert (0x200 <= self.PC <= 0xFFE)
        return self.RAM[self.PC] << 8 | self.RAM[self.PC + 1]

    def do_display_instruction(self, opcode, screen):
        x = self.V[opcode >> 8 & 0xF]
        y = self.V[opcode >> 4 & 0xF]
        n = opcode & 0xF  # number of lines in the sprite to read
        memloc = self.I
        collision = 0
        for i in range(n):
            if screen.xor8px(x, y + i, self.RAM[memloc]):
                collision = 1
            memloc += 1
        self.V[0xF] = collision
        screen.draw()

    def cycle(self, screen):
        opcode = self.fetch()
        increment_pc = True
        if opcode == 0x00E0:
            screen.clear()
        elif opcode >> 12 == 0x1:
            self.PC = opcode & 0xFFF
            increment_pc = False
        elif opcode >> 12 == 0x6:
            whichreg = opcode >> 8 & 0xF
            self.V[whichreg] = opcode & 0xFF
        elif opcode >> 12 == 0x7:
            whichreg = opcode >> 8 & 0xF
            newval = self.V[whichreg] + (opcode & 0xFF)
            if newval > 255:
                self.V[0xF] = 1
                newval &= 0xFF
            else:
                self.V[0xF] = 0
            self.V[whichreg] = newval
        elif opcode >> 12 == 0xA:
            self.I = opcode & 0xFFF
        elif opcode >> 12 == 0xD:
            self.do_display_instruction(opcode, screen)
        else:
            raise OpCodeNotImplementedException
        if increment_pc:
            self.PC += 2

class C8Screen:
    def __init__(self, window, xsize = 64, ysize = 32):
        # self.vram = [[0 for i in range(64)] for j in range(32)]
        self.xsize = xsize
        self.ysize = ysize
        self.vram = array('B', [0 for i in range(self.xsize * self.ysize)])
        self.window = window
        self.clear()

    def clear(self):
        for i in range(self.xsize * self.ysize):
            self.vram[i] = 0

    def setpx(self, x, y, val):
        assert val in (0, 1)
        assert 0 <= x <= self.xsize
        assert 0 <= y <= self.ysize
        self.vram[(y * self.xsize) + x] = val

    def xor8px(self, x, y, val):
        assert 0 <= val <= 0xFF
        assert 0 <= x < self.xsize
        assert 0 <= y <= self.ysize

        # xors the 8 cells from (x,y) to (x+7,y) with the bits in val
        vramcell = (y * self.xsize) + x

        # avoid wrapping
        numpx = min([8, self.xsize - x])

        collision = False

        for i in range(numpx):
            if (val >> i) & 0x1:
                # 0 means do nothing, so only treat the 1 case
                if self.vram[vramcell] == 1:
                    collision = True
                    self.vram[vramcell] = 0
                else:
                    self.vram[vramcell] = 1
            vramcell += 1
        return(collision)

    def draw(self):
        for x in range(64):
            for y in range(32):
                startx = x*SCALE_FACTOR
                starty = y*SCALE_FACTOR
                if self.vram[(y * self.xsize) + x] == 0:
                    color = PIXEL_OFF
                else:
                    color = PIXEL_ON
                for i in range(SCALE_FACTOR):
                    for j in range(SCALE_FACTOR):
                        self.window.set_at((startx + i, starty + j), color)

def main():

    c8 = C8Computer()
    c8.load_rom("IBMLogo.ch8")

    pygame.mixer.pre_init(44100, -16, 1, 1024)
    pygame.init()
    window = pygame.display.set_mode((64 * SCALE_FACTOR, 32 * SCALE_FACTOR))
    pygame.display.set_caption("Fred's CHIP-8 Emulator")
    window.fill(0)

    beep = pygame.mixer.Sound(build_pygame_sound_samples())
    beep.set_volume(0.1)

    run = True
    myscreen = C8Screen(window)
    display_cycle = 0
    px = py = 0

    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
                c8.debug_dump()
            try:
                c8.cycle(myscreen)
            except:
                c8.debug_dump()
                pygame.display.flip()
                raise

            '''
            if event.type == pygame.MOUSEBUTTONDOWN:
                myscreen.setpx(px,py,1)
                myscreen.draw()
                px += 1
                if px % 2 == 0:
                    py += 1
            elif event.type == pygame.KEYDOWN:
                beep.play(-1)
            elif event.type == pygame.KEYUP:
                beep.stop()
            '''

        # Other CHIP-8 authors have said the game crawls if pygame display is updated each cycle
        if display_cycle == 0:
            pygame.display.flip()
            display_cycle = DISPLAY_CYCLES
        else:
            display_cycle -= 1

    pygame.quit()

if __name__ == "__main__":
    # call the main function
    main()


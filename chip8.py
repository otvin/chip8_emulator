import pygame
from array import array
import datetime
import random
from time import sleep

SCALE_FACTOR = 16
PIXEL_OFF = (0, 0, 0)
PIXEL_ON = (255, 255, 255)

# Config options to pass tests
INCREMENT_I_FX55_FX65 = False  # False is the modern way; True matches original
SHIFT_VY_8XY6_8XYE = False  # False is the modern way; True matches original

# The keyboard layout for the CHIP-8 assumes:
#   1 2 3 C
#   4 5 6 D
#   7 8 9 E
#   A 0 B F
#
# Mapping that to our keyboard we use the keys starting with 1, 2, 3, 4
KEYMAPPING = {
    pygame.K_1: 0x01,
    pygame.K_2: 0x02,
    pygame.K_3: 0x03,
    pygame.K_4: 0x0C,
    pygame.K_q: 0x04,
    pygame.K_w: 0x05,
    pygame.K_e: 0x06,
    pygame.K_r: 0x0D,
    pygame.K_a: 0x07,
    pygame.K_s: 0x08,
    pygame.K_d: 0x09,
    pygame.K_f: 0x0E,
    pygame.K_z: 0x0A,
    pygame.K_x: 0x00,
    pygame.K_c: 0x0B,
    pygame.K_v: 0x0F
}

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

    def __init__(self, beep):
        # 4096 Bytes of RAM
        self.RAM = array('B', [0 for i in range(4096)])
        # The 16 registers are named V0..VF
        self.V = array('B', [0 for i in range(16)])
        # Special-purpose 16-bit register; low 12 are used for an address
        self.I = 0
        self.delay_register = 0
        self.delay_register_last_tick_time = None
        self.sound_register = 0
        self.sound_register_last_tick_time = None
        # Program Counter
        self.PC = 0x200
        # One could use RAM for the stack and use a stack pointer but this is easier
        self.stack = []
        self.load_font_sprites()
        self.beep = beep
        self.key_pressed = None

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
        # assert (self.PC % 2 == 0)
        # Cannot exceed RAM boundary for programs
        assert (0x200 <= self.PC <= 0xFFE)
        return self.RAM[self.PC] << 8 | self.RAM[self.PC + 1]

    def do_display_instruction(self, opcode, screen):
        # See https://laurencescotford.com/chip-8-on-the-cosmac-vip-drawing-sprites/ for behavior
        # if sprite is being entirely written off screen.
        x = self.V[opcode >> 8 & 0xF] & 0x3F
        y = self.V[opcode >> 4 & 0xF] & 0x1F
        n = opcode & 0xF  # number of lines in the sprite to read
        memloc = self.I
        collision = 0
        for i in range(n):
            if screen.xor8px(x, y + i, self.RAM[memloc]):
                collision = 1
            memloc += 1
        self.V[0xF] = collision
        screen.draw()


    def decrement_sound_delay_registers(self):
        curtime = datetime.datetime.now()
        if self.delay_register > 0:
            tickdiff = ((curtime - self.delay_register_last_tick_time).microseconds) // 1666
            if tickdiff > 0:
                self.delay_register -= tickdiff
                if self.delay_register < 0:
                    self.delay_register = 0
                    self.delay_register_last_tick_time = None
                else:
                    self.delay_register_last_tick_time = curtime
        if self.sound_register > 0:
            tickdiff = ((curtime - self.sound_register_last_tick_time).microseconds) // 1666
            if tickdiff > 0:
                self.sound_register -= tickdiff
                if self.sound_register < 0:
                    self.sound_register = 0
                    self.sound_register_last_tick_time = None
                    self.beep.stop()
                else:
                    self.sound_register_last_tick_time = curtime

    def cycle(self, screen):
        # decrement timers
        if self.delay_register > 0 or self.sound_register > 0:
            self.decrement_sound_delay_registers()

        opcode = self.fetch()
        print("{}: {} (PC:{})".format(str(datetime.datetime.now()), hex(opcode).upper(), hex(self.PC).upper()))
        increment_pc = True
        if opcode == 0x00E0:
            screen.clear()
        elif opcode == 0x00EE:
            assert len(self.stack) > 0
            self.PC = self.stack.pop()
        elif opcode >> 12 == 0x1:
            self.PC = opcode & 0xFFF
            increment_pc = False
        elif opcode >> 12 == 0x2:
            self.stack.append(self.PC)
            self.PC = opcode & 0xFFF
            increment_pc = False
        elif opcode >> 12 == 0x3:
            # skip next instruction if Vx = kk
            whichreg = opcode >> 8 & 0xF
            if self.V[whichreg] == opcode & 0xFF:
                self.PC += 2
        elif opcode >> 12 == 0x4:
            # skip next instruction if Vx != kk
            whichreg = opcode >> 8 & 0xF
            if self.V[whichreg] != opcode & 0xFF:
                self.PC += 2
        elif opcode >> 12 == 0x5:
            # skip next instruction if Vx = Vy
            reg1 = opcode >> 8 & 0xF
            reg2 = opcode >> 4 & 0xF
            if self.V[reg1] == self.V[reg2]:
                self.PC += 2
        elif opcode >> 12 == 0x6:
            whichreg = opcode >> 8 & 0xF
            self.V[whichreg] = opcode & 0xFF
        elif opcode >> 12 == 0x7:  # Add without a carry bit
            whichreg = opcode >> 8 & 0xF
            self.V[whichreg]  = (self.V[whichreg] + (opcode & 0xFF)) & 0xFF
        elif opcode >> 12 == 0x8:
            reg1 = opcode >> 8 & 0xF
            reg2 = opcode >> 4 & 0xF
            vx = self.V[reg1]
            vy = self.V[reg2]
            oper = opcode & 0xF
            if oper == 0x0:
                self.V[reg1] = vy
            elif oper == 0x1:
                self.V[reg1] = vx | vy
                self.V[0xF] = 0
            elif oper == 0x2:
                self.V[reg1] = vx & vy
                self.V[0xF] = 0
            elif oper == 0x3:
                self.V[reg1] = vx ^ vy
                self.V[0xF] = 0
            elif oper == 0x4:
                sum = vx + vy
                if sum > 255:
                    carry = 1
                else:
                    carry = 0
                self.V[reg1] = sum & 0xFF
                self.V[0xF] = carry
            elif oper == 0x5:
                if vx > vy:
                    notborrow = 1
                else: notborrow = 0
                self.V[reg1] = (vx - vy) & 0xFF
                self.V[0xF] = notborrow
            elif oper == 0x6:  # Shift Right by 1
                if SHIFT_VY_8XY6_8XYE:
                    # Original: copied vy into vx, then shifted vx
                    # Modern: shifted vx in place, ignored vy
                    # See: https://tobiasvl.github.io/blog/write-a-chip-8-emulator/#8xy6-and-8xye-shift
                    vx = vy
                lsb = vx & 0x1
                self.V[reg1] = vx >> 1
                self.V[0xF] = lsb
            elif oper == 0x7:
                if vy > vx:
                    notborrow = 1
                else:
                    notborrow = 0
                self.V[reg1] = (vy - vx) & 0xFF
                self.V[0xF] = notborrow
            elif oper == 0xE:  # Shift Left by 1
                if SHIFT_VY_8XY6_8XYE:
                    vx = vy
                msb = vx & 0x80
                self.V[reg1] = (vx << 1 & 0xFF)
                if msb:
                    self.V[0xF] = 0x1
                else:
                    self.V[0xF] = 0x0
            else:
                raise OpCodeNotImplementedException(hex(opcode))
        elif opcode >> 12 == 0x9 and opcode & 0xF == 0:
            reg1 = opcode >> 8 & 0xF
            reg2 = opcode >> 4 & 0xF
            vx = self.V[reg1]
            vy = self.V[reg2]
            if vx != vy:
                self.PC += 2
        elif opcode >> 12 == 0xA:
            self.I = opcode & 0xFFF
        elif opcode >> 12 == 0xB:
            self.PC = (opcode & 0xFFF) + self.V[0]
            increment_pc = False
        elif opcode >> 12 == 0xC:
            reg = opcode >> 8 & 0xF
            kk = opcode & 0xFF
            self.V[reg] = random.randrange(0, 255) & kk
        elif opcode >> 12 == 0xD:
            self.do_display_instruction(opcode, screen)
        elif opcode >> 12 == 0xE:
            if opcode & 0xFF == 0x9E:
                reg = opcode >> 8 & 0xF
                if self.key_pressed is not None and self.key_pressed == self.V[reg]:
                    self.PC += 2
            elif opcode & 0xFF == 0xA1:
                reg = opcode >> 8 & 0xF
                if self.key_pressed is None:
                    self.PC += 2
                elif self.key_pressed != self.V[reg]:
                    self.PC += 2
            else:
                raise OpCodeNotImplementedException(hex(opcode))
        elif opcode >> 12 == 0xF:
            oper = opcode & 0xFF
            reg = (opcode >> 8) & 0xF
            if oper == 0x07:
                self.V[reg] = self.delay_register
            elif oper == 0x0A:
                if self.key_pressed is None:
                    increment_pc = False  # do nothing
                else:
                    reg = opcode >> 8 & 0xF
                    self.V[reg] = self.key_pressed
            elif oper == 0x15:
                self.delay_register = self.V[reg]
                if self.delay_register > 0:
                    self.delay_register_last_tick_time = datetime.datetime.now()
            elif oper == 0x18:
                self.sound_register = self.V[reg]
                if self.sound_register > 0:
                    self.sound_register_last_tick_time = datetime.datetime.now()
                    self.beep.play(-1)
            elif oper == 0x1E:
                # I don't believe we check for overflow here.
                self.I += self.V[reg]
                self.I &= 0xFFF
            elif oper == 0x29:
                # each character is 5 bytes, 0 starts at 0x00 in memory
                assert (self.V[reg] <= 0xF)
                self.I = 5 * self.V[reg]
            elif oper == 0x33:
                val = self.V[reg]
                hundreds = val // 100
                tens = (val - (100 * hundreds)) // 10
                ones = val % 10
                self.RAM[self.I] = hundreds
                self.RAM[self.I + 1] = tens
                self.RAM[self.I + 2] = ones
            elif oper == 0x55:
                # Note that in the original CHIP-8 on the COSMAC VIP, I was incremented during this
                # loop.  See: https://laurencescotford.com/chip-8-on-the-cosmac-vip-loading-and-saving-variables/
                # However, modern interpreters do not increment I.  So need a config option in order to pass.
                x = (opcode >> 8) & 0xF
                oldI = self.I
                for i in range(x + 1):
                    self.RAM[self.I] = self.V[i]
                    self.I += 1
                if not INCREMENT_I_FX55_FX65:
                    self.I = oldI
            elif oper == 0x65:
                x = (opcode >> 8) & 0xF
                oldI = self.I
                for i in range(x + 1):
                    self.V[i] = self.RAM[self.I]
                    self.I += 1
                if not INCREMENT_I_FX55_FX65:
                    self.I = oldI
            else:
                raise OpCodeNotImplementedException(hex(opcode))
        else:
            raise OpCodeNotImplementedException(hex(opcode))
        if increment_pc:
            self.PC += 2

class C8Screen:
    def __init__(self, window, pygame, xsize=64, ysize=32):
        # self.vram = [[0 for i in range(64)] for j in range(32)]
        self.xsize = xsize
        self.ysize = ysize
        self.pygame = pygame
        self.vram = array('B', [0 for i in range(self.xsize * self.ysize)])
        self.window = window
        self.clear()

    def clear(self):
        for i in range(self.xsize * self.ysize):
            self.vram[i] = 0
        self.draw()

    def setpx(self, x, y, val):
        assert val in (0, 1)
        assert 0 <= x <= self.xsize
        assert 0 <= y <= self.ysize
        self.vram[(y * self.xsize) + x] = val

    def xor8px(self, x, y, val):
        assert 0 <= val <= 0xFF
        assert 0 <= x
        assert 0 <= y

        # xors the 8 cells from (x,y) to (x+7,y) with the bits in val
        vramcell = (y * self.xsize) + x

        # avoid wrapping
        numpx = min([8, self.xsize - x])
        if y >= 32:
            return

        collision = False

        for i in range(numpx):
            if (val << i) & 0x80:
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
        pygame.display.update()

def main():

    global INCREMENT_I_FX55_FX65, SHIFT_VY_8XY6_8XYE

    pygame.mixer.pre_init(44100, -16, 1, 1024)
    pygame.init()
    window = pygame.display.set_mode((64 * SCALE_FACTOR, 32 * SCALE_FACTOR))
    pygame.display.set_caption("Fred's CHIP-8 Emulator")
    window.fill(0)

    beep = pygame.mixer.Sound(build_pygame_sound_samples())
    beep.set_volume(0.1)

    c8 = C8Computer(beep)

    c8.load_rom("IBMLogo.ch8")  # PASSES

    # Both of these tests require that I not be incremented in Fx55 and Fx65
    # https://github.com/daniel5151/AC8E/tree/master/roms
    # INCREMENT_I_FX55_FX65 = False
    # c8.load_rom("BC_test.ch8")  # FAILS with error "16" which says I have an Fx55 / Fx65 problem
    # https://github.com/Skosulor/c8int/tree/master/test
    # INCREMENT_I_FX55_FX65 = False
    # c8.load_rom("c8_test.c8")  # FAILS with error "18" which says I have an Fx55 / Fx65 problem

    # c8.load_rom("test_opcode.ch8")   # PASSES

    # https://github.com/Timendus/chip8-test-suite/
    # INCREMENT_I_FX55_FX65 = True  # to be faithful to the CHIP-8
    # SHIFT_VY_8XY6_8XYE = True
    # c8.load_rom("chip8-test-suite.ch8")  # PASSES but haven't tested keyboard yet

    run = True
    myscreen = C8Screen(window, pygame)

    start_time = datetime.datetime.now()
    num_instr = 0
    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
                c8.debug_dump()
            elif event.type == pygame.KEYDOWN:
                if event.key in KEYMAPPING.keys():
                    c8.key_pressed = KEYMAPPING[event.key]
            elif event.type == pygame.KEYUP:
                # we can get into a weird state if multiple keys are pressed, one, one is let up, and the other is
                # pressed.
                c8.key_pressed = None

        try:
            c8.cycle(myscreen)
            num_instr += 1
        except:
            c8.debug_dump()
            pygame.display.flip()
            raise
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("Start: {}".format(start_time))
    print("End: {}".format(end_time))
    print("Duration: {} sec.".format(duration))
    print("Performance: {} instructions per second".format(num_instr / duration))

    pygame.quit()

if __name__ == "__main__":
    # call the main function
    main()


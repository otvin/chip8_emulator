import pygame
from array import array
import datetime
import random

SCALE_FACTOR = 8
PIXEL_OFF = (0, 0, 0)
PIXEL_ON = (255, 255, 255)

# Config options to cover differences between modern CHIP-8 interpreters and the original
INCREMENT_I_FX55_FX65 = False  # False is the modern way; True matches original
SHIFT_VY_8XY6_8XYE = False  # False is the modern way; True matches original
# Tweak this per ROM - how many microseconds to wait before executing an instruction.  Smaller means more frequent
# instruction executions, which makes things faster.
INSTRUCTION_DELAY = 2000


# The keyboard layout for the CHIP-8 assumes:
#   1 2 3 C
#   4 5 6 D
#   7 8 9 E
#   A 0 B F
#
# We map this to the following keys on our keyboard:
#   1 2 3 4
#   Q W E R
#   A S D F
#   Z X C V

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

    def __init__(self, screen, beep):
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
        # One could use RAM for the stack and use a stack pointer but a python List is simpler.
        self.stack = []
        self.load_font_sprites()
        self.beep = beep
        self.screen = screen
        self.keys_pressed = [0 for i in range(16)]  # used for the Ex9E and ExA1 instructions
        self.blocking_on_fx0a = False
        self.fx0a_key_pressed = None
        self.fx0a_key_up = None

        # Using a list of functions to speed the lookup, vs. doing a big nested
        # if/else.  There is one instruction for each of the high-order nibbles
        # 1, 2, 3, 4, 5, 6, 7, 9, A, B, and C.  The others (0, 8, E, F) have
        # multiple.
        self.operation_list = [
            self._0_opcodes, self._1nnn, self._2nnn, self._3xkk, self._4xkk, self._5xy0,
            self._6xkk, self._7xkk, self._8_opcodes, self._9xy0, self._Annn, self._Bnnn,
            self._Cxkk, self._Dxyn, self._E_opcodes, self._F_opcodes
        ]

        # opcodes beginning with 8 can be determined based on the least-significant
        # nibble (0..7 and E)
        self._8_operations = [
            self._8xy0, self._8xy1, self._8xy2, self._8xy3, self._8xy4, self._8xy5,
            self._8xy6, self._8xy7, self.invalid_op, self.invalid_op,
            self.invalid_op, self.invalid_op, self.invalid_op, self.invalid_op,
            self._8xyE, self.invalid_op
        ]

        # opcodes beginning with F can be determined based on the least_significant
        # byte (07, 0A, 15, 18, 1E, 29, 33, 55, and 65).  Since this is sparse,
        # will use a dictionary.
        self._F_operations = {
            0x07 : self._Fx07,
            0x0A : self._Fx0A,
            0x15 : self._Fx15,
            0x18 : self._Fx18,
            0x1E : self._Fx1E,
            0x29 : self._Fx29,
            0x33 : self._Fx33,
            0x55 : self._Fx55,
            0x65 : self._Fx65
        }

    def debug_dump(self):
        outfile = open("debug.txt", "w")
        outfile.write("PC: 0x{}\n".format(hex(self.PC).upper()[2:]))
        outfile.write("Next instr.: 0x{}\n".format(hex(self.RAM[self.PC] << 8 | self.RAM[self.PC + 1]).upper()[2:]))
        outfile.write("I: 0x{}\n".format(hex(self.I).upper()[2:]))
        for i in range(16):
            outfile.write("V{}: 0x{}".format(hex(i).upper()[2], hex(self.V[i])[2:].zfill(2).upper()))
            if i % 4 == 3:
                outfile.write('\n')
            else:
                outfile.write('\t')
        outfile.write("delay register: 0x{}\n".format(hex(self.delay_register).upper()[2:]))
        outfile.write("sound register: 0x{}\n".format(hex(self.sound_register).upper()[2:]))
        outfile.write("stack: [")
        if len(self.stack) > 0:
            for i in range(len(self.stack) - 1):
                outfile.write("0x{}, ".format(hex(self.stack[i]).upper()[2:]))
            outfile.write("0x{}]\n".format(hex(self.stack[-1]).upper()[2:]))
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

    def decrement_sound_delay_registers(self):
        curtime = datetime.datetime.now()
        if self.delay_register > 0:
            tickdiff = int((curtime - self.delay_register_last_tick_time).total_seconds() * 1000000) // 16666
            if tickdiff > 0:
                self.delay_register -= tickdiff
                if self.delay_register <= 0:
                    self.delay_register = 0
                    self.delay_register_last_tick_time = None
                else:
                    self.delay_register_last_tick_time = curtime
        if self.sound_register > 0:
            tickdiff = int((curtime - self.sound_register_last_tick_time).total_seconds() * 1000000)  // 16666
            if tickdiff > 0:
                self.sound_register -= tickdiff
                if self.sound_register <= 0:
                    self.sound_register = 0
                    self.sound_register_last_tick_time = None
                    self.beep.stop()
                else:
                    self.sound_register_last_tick_time = curtime

    def _0_opcodes(self, opcode, vx, vy, n, kk, nnn):
        if opcode == 0x00E0:
            # 00E0 - CLS
            # clear the screen
            self.screen.clear()
        elif opcode == 0x00EE:
            # 00EE - RET
            # Return from a subroutine
            assert len(self.stack) > 0
            self.PC = self.stack.pop()
        else:
            raise InvalidOpCodeException(opcode)
        return True

    def _1nnn(self, opcode, vx, vy, n, kk, nnn):
        # 1nnn - JP addr
        # Jump to location nnn
        self.PC = nnn
        return False

    def _2nnn(self, opcode, vx, vy, n, kk, nnn):
        # 2nnn - CALL addr
        # Call subroutine at nnn
        self.stack.append(self.PC)
        # Technically - should check for stack overflow but not going to worry about it
        self.PC = nnn
        return False

    def _3xkk(self, opcode, vx, vy, n, kk, nnn):
        # 3xkk - SE Vx, byte
        # Skip next instruction if Vx == kk
        if self.V[vx] == kk:
            self.PC += 2
        return True

    def _4xkk(self, opcode, vx, vy, n, kk, nnn):
        # 4xkk - SNE Vx, byte
        # Skip next instruction if Vx != kk
        if self.V[vx] != kk:
            self.PC += 2
        return True

    def _5xy0(self, opcode, vx, vy, n, kk, nnn):
        # 5xy0 - SE Vx, Vy
        # Skip next instruction if Vx == Vy
        if n != 0:
            raise InvalidOpCodeException(opcode)
        if self.V[vx] == self.V[vy]:
            self.PC += 2
        return True

    def _6xkk(self, opcode, vx, vy, n, kk, nnn):
        # 6xkk - LD Vx, byte
        # Set Vx = kk
        self.V[vx] = kk
        return True

    def _7xkk(self, opcode, vx, vy, n, kk, nnn):
        # 7xkk - ADD Vx, byte
        # Add value in kk to vx, stores result in vx, does NOT set overflow flag
        self.V[vx] = (self.V[vx] + kk) & 0xFF
        return True

    def invalid_op(self, opcode, vx, vy):
        raise InvalidOpCodeException(opcode)

    def _8xy0(self, opcode, vx, vy):
        # 8xy0 - LD Vx, Vy
        # Set Vx = Vy
        self.V[vx] = self.V[vy]
        return True

    def _8xy1(self, opcode, vx, vy):
        # 8xy1 - OR Vx, Vy
        # Set Vx = Vx OR Vy.
        # Historical quick: this op also set VF = 0
        self.V[vx] = self.V[vx] | self.V[vy]
        self.V[0xF] = 0
        return True

    def _8xy2(self, opcode, vx, vy):
        # 8xy2 - AND Vx, Vy
        # Set Vx = Vx AND Vy
        # Historical quick: this op also set VF = 0
        self.V[vx] = self.V[vx] & self.V[vy]
        self.V[0xF] = 0
        return True

    def _8xy3(self, opcode, vx, vy):
        # 8xy3 - XOR Vx, Vy
        # Set Vx = Vx XOR Vy
        # Historical quick: this op also set VF = 0
        self.V[vx] = self.V[vx] ^ self.V[vy]
        self.V[0xF] = 0
        return True

    def _8xy4(self, opcode, vx, vy):
        # 8xy4 - ADD Vx, Vy
        # Set Vx = Vx + Vy, set VF = carry.  Must be done in this order.
        sum = self.V[vx] + self.V[vy]
        self.V[vx] = sum & 0xFF
        if sum > 255:
            self.V[0xF] = 1
        else:
            self.V[0xF] = 0
        return True

    def _8xy5(self, opcode, vx, vy):
        # 8xy5 - SUB Vx, Vy
        # Set Vx = Vx - Vy.  Set VF = NOT borrow (VF = 1 if Vx > Vy)
        if self.V[vx] > self.V[vy]:
            notborrow = 1
        else:
            notborrow = 0
        self.V[vx] = (self.V[vx] - self.V[vy]) & 0xFF
        self.V[0xF] = notborrow
        return True

    def _8xy6(self, opcode, vx, vy):
        # 8xy6 - SHR Vx, Vy
        # ORIGINAL IMPLEMENTATION: copy Vy into Vx, then shift Vx right by 1.
        # MODERN IMPLEMENTATION: shift Vx right by 1 in place
        # In both, VF is set to the least significant bit of Vx before the shift
        # See: https://tobiasvl.github.io/blog/write-a-chip-8-emulator/#8xy6-and-8xye-shift
        if SHIFT_VY_8XY6_8XYE:
            self.V[vx] = self.V[vy]
        lsb = self.V[vx] & 0x1
        self.V[vx] = self.V[vx] >> 1
        self.V[0xF] = lsb
        return True

    def _8xy7(self, opcode, vx, vy):
        # 8xy7 - SUBN Vx, Vy
        # Set Vx = Vy - Vx.  Set VF = NOT borrow (VF = 1 if Vy > Vx)
        if self.V[vy] > self.V[vx]:
            notborrow = 1
        else:
            notborrow = 0
        self.V[vx] = (self.V[vy] - self.V[vx]) & 0xFF
        self.V[0xF] = notborrow
        return True

    def _8xyE(self, opcode, vx, vy):
        # 8xyE - SHL Vx, Vy
        # ORIGINAL IMPLEMENTATION: copy Vy into Vx, then shift Vx left by 1.
        # MODERN IMPLEMENTATION: shift Vx left by 1 in place.
        # In both, VF is set to the most significant bit of Vx before the shift
        if SHIFT_VY_8XY6_8XYE:
            self.V[vx] = self.V[vy]
        msb = self.V[vx] & 0x80
        self.V[vx] = (self.V[vx] << 1) & 0xFF
        if msb:
            self.V[0xF] = 0x1
        else:
            self.V[0xF] = 0x0
        return True

    def _8_opcodes(self, opcode, vx, vy, n, kk, nnn):
        return self._8_operations[n](opcode, vx, vy)

    def _9xy0(self, opcode, vx, vy, n, kk, nnn):
        # 9xy0 - SNE Vx, Vy
        # Skip next instruction if Vx != Vy
        if n != 0:
            raise InvalidOpCodeException(opcode)
        if self.V[vx] != self.V[vy]:
            self.PC += 2
        return True

    def _Annn(self, opcode, vx, vy, n, kk, nnn):
        # Annn - LD I, addr
        # The value of register I is set to nnn
        self.I = nnn
        return True

    def _Bnnn(self, opcode, vx, vy, n, kk, nnn):
        # Bnnn - JP V0, addr
        # The program counter is set to nnn plus the value of V0
        self.PC = nnn + self.V[0]
        return False

    def _Cxkk(self, opcode, vx, vy, n, kk, nnn):
        # Cxkk - RND Vx, byte
        # Set Vx = random byte AND kk
        self.V[vx] = random.randrange(0, 255) & kk
        return True

    def _Dxyn(self, opcode, vx, vy, n, kk, nnn):
        # See https://laurencescotford.com/chip-8-on-the-cosmac-vip-drawing-sprites/ for behavior
        # if sprite is being entirely written off screen.
        x = self.V[vx] & 0x3F
        y = self.V[vy] & 0x1F
        memloc = self.I
        collision = 0
        for i in range(n):
            if self.screen.xor8px(x, y + i, self.RAM[memloc]):
                collision = 1
            memloc += 1
        self.V[0xF] = collision
        self.screen.draw_rect_list.append((x, y, min([x + 8, self.screen.xsize]), min([y + n, self.screen.ysize])))
        return True

    def _E_opcodes(self, opcode, vx, vy, n, kk, nnn):
        if kk == 0x9E:
            # Ex9E - SKP Vx
            # Skip next instruction if key with value of Vx is pressed
            if self.keys_pressed[self.V[vx]]:
                self.PC += 2
        elif kk == 0xA1:
            # ExA1 - SKNP Vx
            # Skip next instruction if key with value of Vx is NOT pressed
            if not self.keys_pressed[self.V[vx]]:
                self.PC += 2
        else:
            raise InvalidOpCodeException(opcode)
        return True

    def _Fx07(self, vx):
        # Fx07 - LD Vx, DT
        # The value of the Delay Timer is placed into Vx.
        self.V[vx] = self.delay_register
        return True

    def _Fx0A(self, vx):
        # Fx0A - LD, Vx, Key
        # Wait for a key press, store the value of the key in Vx
        # NOTE: The original CHIP-8 waited until a key was pressed and then released.
        # Cowgod's definition is unclear on this point.
        increment_pc = False  # assume we block here.
        if not self.blocking_on_fx0a:
            self.blocking_on_fx0a = True
            self.fx0a_key_pressed = None
            self.fx0a_key_up = None
        else:
            if self.fx0a_key_up is None:
                pass  # do nothing
            else:
                self.V[vx] = self.fx0a_key_up
                self.blocking_on_fx0a = False
                self.fx0a_key_up = None
                self.fx0a_key_pressed = None
                increment_pc = True
        return increment_pc

    def _Fx15(self, vx):
        # Fx15 - LD DT, Vx
        # Set Delay Timer = Vx
        self.delay_register = self.V[vx]
        if self.delay_register > 0:
            self.delay_register_last_tick_time = datetime.datetime.now()
        return True

    def _Fx18(self, vx):
        # Fx18 - LD ST, Vx
        # Set Sound Timer = Vx
        self.sound_register = self.V[vx]
        if self.sound_register > 0:
            self.sound_register_last_tick_time = datetime.datetime.now()
            self.beep.play(-1)
        return True

    def _Fx1E(self, vx):
        # Fx1E - Set I = I + Vx - do not set the overflow flag
        self.I += self.V[vx] & 0xFFF
        return True

    def _Fx29(self, vx):
        # Fx29 - LD F, Vx
        # Set I = location of sprite for digit Vx ("F" = Font)
        # each character is 5 bytes, with "0" starting at 0x00 in memory
        assert (self.V[vx] <= 0xF)
        self.I = 5 * self.V[vx]
        return True

    def _Fx33(self, vx):
        # Fx33 - LD B, Fx
        # Store binary coded decimal value of Vx in memory locations I, I+1, I+2
        # Convert Vx to base 10, place the hundreds digit in I, tens digit in I+1, ones in I+2
        val = self.V[vx]
        hundreds = val // 100
        tens = (val - (100 * hundreds)) // 10
        ones = val % 10
        self.RAM[self.I] = hundreds
        self.RAM[self.I + 1] = tens
        self.RAM[self.I + 2] = ones
        return True

    def _Fx55(self, vx):
        # Fx55 - LD[I], Vx
        # Store registers V0 through Vx in memory starting at location I
        # Note that in the original CHIP-8 on the COSMAC VIP, I was incremented during this
        # loop.  See: https://laurencescotford.com/chip-8-on-the-cosmac-vip-loading-and-saving-variables/
        # However, modern interpreters do not increment I.  So need a config option in order to pass.
        oldI = self.I
        for i in range(vx + 1):
            self.RAM[self.I] = self.V[i]
            self.I += 1
        if not INCREMENT_I_FX55_FX65:
            self.I = oldI
        return True

    def _Fx65(self, vx):
        # Fx65 - LD Vx, [I]
        # Read values from memory starting at location I into registers V0 through Vx
        oldI = self.I
        for i in range(vx + 1):
            self.V[i] = self.RAM[self.I]
            self.I += 1
        if not INCREMENT_I_FX55_FX65:
            self.I = oldI
        return True

    def _F_opcodes(self, opcode, vx, vy, n, kk, nnn):
        if kk in self._F_operations.keys():
            return self._F_operations[kk](vx)
        else:
            raise InvalidOpCodeException(opcode)

    def cycle(self, screen):
        '''
        Instructions have one of 6 patterns:
        All 4 bytes fixed:
            00E0, 00EE
        Operation + nnn (address)
            1nnn, 2nnn, Annn, Bnnn
        Operation + Vx + kk (byte)
            3xkk, 4xkk, 6xkk, 7xkk, Cxkk
        Operation + Vx + Vy + nibble-type
            5xy0, 8xy0, 8xy1, 8xy2, 8xy3,
            8xy4, 8xy5, 8xy6, 8xy7, 8xye
        Operation + Vx + Vy + n (nibble)
            Dxyn
        Operation + Vx + byte-type
            Ex9E, ExA1, Fx07, Fx0A, Fx15,
            Fx18, Fx1E, Fx29, Fx33, Fx55,
            Fx65

        To minimize redundant code, calculate all the possible ways
        to parse the opcode and then later use only the ones that are needed
        '''

        opcode = self.fetch()
        operation = opcode >> 12
        vx = opcode >> 8 & 0xF
        vy = opcode >> 4 & 0xF
        n = opcode & 0xF
        nnn = opcode & 0xFFF
        kk = opcode & 0xFF
        increment_pc = self.operation_list[operation](opcode, vx, vy, n, kk, nnn)
        if increment_pc:
            self.PC += 2

class C8Screen:
    def __init__(self, window, pygame, xsize=64, ysize=32):
        self.xsize = xsize
        self.ysize = ysize
        self.pygame = pygame
        self.vram = array('B', [0 for i in range(self.xsize * self.ysize)])
        self.window = window
        self.num_renders = 0
        self.render_time_ps = 0
        self.draw_rect_list = []
        self.clear()
        self.needs_draw = False
        self.last_draw_time = datetime.datetime.now()

    def clear(self):
        for i in range(self.xsize * self.ysize):
            self.vram[i] = 0
        self.draw_rect_list.append((0, 0, self.xsize, self.ysize))
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
        self.needs_draw = True
        return collision

    def draw(self):
        self.num_renders += 1
        start_time = datetime.datetime.now()
        pygamerects = []
        for item in self.draw_rect_list:
            for x in range(item[0], item[2]):
                for y in range(item[1], item[3]):
                    startx = x * SCALE_FACTOR
                    starty = y * SCALE_FACTOR
                    if self.vram[(y * self.xsize) + x] == 0:
                        color = PIXEL_OFF
                    else:
                        color = PIXEL_ON
                    for i in range(SCALE_FACTOR):
                        for j in range(SCALE_FACTOR):
                            self.window.set_at((startx + i, starty + j), color)
            rectx = item[0] * SCALE_FACTOR
            recty = item[1] * SCALE_FACTOR
            rect_width = (item[2] - item[0]) * SCALE_FACTOR
            rect_height = (item[3] - item[1]) * SCALE_FACTOR
            pygamerects.append(pygame.Rect(rectx, recty, rect_width, rect_height))
        pygame.display.update(pygamerects)
        self.needs_draw = False
        self.draw_rect_list = []
        self.last_draw_time = datetime.datetime.now()
        self.render_time_ps += (self.last_draw_time - start_time).total_seconds()
def main():

    global INCREMENT_I_FX55_FX65, SHIFT_VY_8XY6_8XYE, INSTRUCTION_DELAY

    pygame.mixer.pre_init(44100, -16, 1, 1024)
    pygame.init()
    window = pygame.display.set_mode((64 * SCALE_FACTOR, 32 * SCALE_FACTOR))
    pygame.display.set_caption("Fred's CHIP-8 Emulator")
    window.fill(0)

    beep = pygame.mixer.Sound(build_pygame_sound_samples())
    beep.set_volume(0.1)

    myscreen = C8Screen(window, pygame)
    c8 = C8Computer(myscreen, beep)

    # https://github.com/Timendus/chip8-test-suite/
    INCREMENT_I_FX55_FX65 = True  # to be faithful to the CHIP-8
    SHIFT_VY_8XY6_8XYE = True
    c8.load_rom("chip8-test-suite.ch8")

    run = True

    start_time = datetime.datetime.now()
    num_instr = 0

    timer_event = pygame.USEREVENT + 1
    pygame.time.set_timer(timer_event, 17)  # 17ms ~= 60Hz

    last_instruction_time = datetime.datetime.now()

    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
                c8.debug_dump()
            elif event.type == pygame.KEYDOWN:
                if event.key in KEYMAPPING.keys():
                    c8.keys_pressed[KEYMAPPING[event.key]] = 1
                    if c8.blocking_on_fx0a:
                        c8.fx0a_key_pressed = KEYMAPPING[event.key]
            elif event.type == pygame.KEYUP:
                # we can get into a weird state if multiple keys are pressed, one, one is let up, and the other is
                # pressed.
                if event.key in KEYMAPPING.keys():
                    c8.keys_pressed[KEYMAPPING[event.key]] = 0
                    if c8.blocking_on_fx0a:
                        if c8.fx0a_key_pressed == KEYMAPPING[event.key]:
                            c8.fx0a_key_up = KEYMAPPING[event.key]
                            c8.fx0a_key_pressed = None
            elif event.type == timer_event:
                c8.decrement_sound_delay_registers()


        curtime = datetime.datetime.now()
        tickdiff = ((curtime - last_instruction_time).total_seconds() * 1000000) / INSTRUCTION_DELAY
        if tickdiff > 0:
            try:
                c8.cycle(myscreen)
                num_instr += 1
                last_instruction_time = curtime
                if num_instr % 8 == 0:   # logic is that the CPU runs at 500 Hz and display at 60 Hz or 1/8th, roughly
                    myscreen.draw()

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
    print("Screen num renders: {}".format(myscreen.num_renders))
    print("Average microseconds per render: {}".format((1000000 * myscreen.render_time_ps) / myscreen.num_renders))

    pygame.quit()


if __name__ == "__main__":
    # call the main function
    main()


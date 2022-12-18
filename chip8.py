import pygame

SCALE_FACTOR = 16

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

    pygame.init()
    window = pygame.display.set_mode((64 * SCALE_FACTOR, 32 * SCALE_FACTOR))
    pygame.display.set_caption("Fred's CHIP-8 Emulator")
    window.fill(0)

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
        pygame.display.flip()


if __name__ == "__main__":
    # call the main function
    main()
    pygame.quit()

import sys
import math
import signal
import shutil


ESC = "\x1b"     # Escape
CSI = f"{ESC}["  # Control sequence introducer

EN_ALT_BUF = "?1049h"   # Enable Alternate Buffer
DIS_ALT_BUF = "?1049l"  # Disable Alternate Buffer

TITLE = "HTTP/TUI"
TITLE_COLOR = 178


def main() -> None:
    if sys.platform == "win32":
        import ansi_win
        driver = ansi_win
    else:
        # TODO implement *nix
        pass

    o_state = driver.initialize()
    enable_buffer()

    def signal_trap(sig, frame) -> None:
        '''Ensures terminal state is restored'''
        disable_buffer()
        driver.reset(o_state)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_trap)

    # Defaults to 80 columns by 24 lines
    terminal_size = shutil.get_terminal_size()
    render_title(terminal_size.columns)

    i = 0
    while i < 100000000:
        i += 1

    disable_buffer()
    driver.reset(o_state)


def enable_buffer() -> None:
    ''' Clears the screen '''
    print(f"{CSI}{EN_ALT_BUF}")


def disable_buffer() -> None:
    ''' Reverts screen back to
    previous state before script '''
    print(f"{CSI}{DIS_ALT_BUF}")


def set_foreground(color: int) -> None:
    print(f"{CSI}38;5;{color}m", end="")


def reset_style() -> None:
    print(f"{CSI}0m", end="")


def render_title(width: int) -> None:
    offset = math.floor(width / 2) - len(TITLE)

    set_foreground(TITLE_COLOR)
    print(f"{' ' * offset}{TITLE}")
    reset_style()

    print(f"{'-' * width}")


if __name__ == "__main__":
    main()

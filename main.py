import sys
import signal
import shutil


ESC = "\x1b"     # Escape
CSI = f"{ESC}["  # Control Sequence Introducer

EN_ALT_BUF = "?1049h"   # Enable Alternate Buffer
DIS_ALT_BUF = "?1049l"  # Disable Alternate Buffer

TITLE = "HTTP/TUI"
TITLE_COLOR = 178


def main() -> None:
    if sys.platform == "win32":
        import ansi_win
        driver = ansi_win
    else:
        import ansi_nix
        driver = ansi_nix

    ostate = driver.initialize()
    enable_buffer()

    def signal_trap(sig, frame) -> None:
        '''Ensures terminal state is restored'''
        disable_buffer()
        driver.reset(ostate)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_trap)

    set_cursor(1, 1)
    # Defaults to 80 columns by 24 lines
    terminal_size = shutil.get_terminal_size()
    render_title(terminal_size.columns)

    f_quit = False  # Flag quit
    while not f_quit:
        key = sys.stdin.read(1)
        if key == driver.KeyCodes.QUIT.value:
            f_quit = True

    disable_buffer()
    driver.reset(ostate)


def enable_buffer() -> None:
    '''Clears the screen'''
    print(f"{CSI}{EN_ALT_BUF}")


def disable_buffer() -> None:
    '''Reverts screen back to
    previous state before script'''
    print(f"{CSI}{DIS_ALT_BUF}")


def set_foreground(color: int) -> None:
    print(f"{CSI}38;5;{color}m", end="")


def reset_style() -> None:
    print(f"{CSI}0m", end="")


def set_cursor(x: int, y: int) -> None:
    '''
    Escape sequence to move the
    cursor with the assumption that
    location (1,1) is at the top
    left of the screen.

    It also assumes that {x} and {y}
    are based on character size.
    '''
    print(f'{CSI}{y};{x}H', end="")


def render_title(width: int) -> None:
    offset = width - (len(TITLE) + 4)
    set_foreground(TITLE_COLOR)
    print(f"{offset * ' '}{TITLE}", end="")
    reset_style()
    set_cursor(1, 2)
    print(f"{'-' * width}")


if __name__ == "__main__":
    main()

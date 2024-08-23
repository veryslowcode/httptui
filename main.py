import math
import shutil


ESC = "\x1b"     # Escape
CSI = f"{ESC}["  # Control sequence indicator

EN_ALT_BUF = "?1049h"   # Enable Alternate Buffer
DIS_ALT_BUF = "?1049l"  # Disabel Alternate Buffer

TITLE = "HTTP/TUI"
TITLE_COLOR = 178


def main() -> None:
    enable_buffer()

    # Defaults to 80 columns by 24 lines
    terminal_size = shutil.get_terminal_size()
    render_title(terminal_size.columns)

    while True:
        pass


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

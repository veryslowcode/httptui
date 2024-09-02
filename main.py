import sys
import math
import shutil
import signal
import argparse
import configparser
from enum import Enum
from pathlib import Path
from dataclasses import dataclass


TITLE = "HTTP/TUI"      # For main application

ESC = "\x1b"            # Escape
CSI = f"{ESC}["         # Control Sequence Introducer

EN_ALT_BUF = "?1049h"   # Enable Alternate Buffer
DIS_ALT_BUF = "?1049l"  # Disable Alternate Buffer


class ColorMode(Enum):
    Bit4 = "4bit"
    Bit8 = "8bit"


@dataclass
class Theme:
    title_color:  int
    border_color: int


@dataclass
class Border:
    t_single = "┬"
    t_double = "╦"
    h_single = "─"
    h_double = "═"
    v_single = "│"
    v_double = "║"


class BorderStyle(Enum):
    Single = "single"
    Double = "double"


@dataclass
class Arguments:
    theme_file: str = "theme.ini"
    color_mode: ColorMode = ColorMode.Bit8
    border_style: BorderStyle = BorderStyle.Single


def main() -> None:
    args = parse_args()
    if sys.platform == "win32":
        _win_main(args)
    else:
        _nix_main(args)


def parse_args() -> Arguments:
    description = "Send and recieve HTTP request in the terminal"
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("-t", "--theme",
                        help="Path to theme file " +
                        "(defaults to 'theme.ini')")
    parser.add_argument("-m", "--mode",
                        help="Color style: '4bit' or '8bit' " +
                        "(defaults to '8bit')")

    parser.add_argument("-b", "--border",
                        help="Border style: 'single' or 'double' " +
                        "(defaults to 'single')")

    args = Arguments()
    parsed_args = parser.parse_args()

    if parsed_args.theme is not None:
        args.theme_file = parsed_args.theme
    else:
        # Ensure we can run this script with anywhere
        scriptdir = Path(__file__).parent
        args.theme_file = Path(scriptdir, "theme.ini")

    if parsed_args.mode is not None:
        mode = (ColorMode)(parsed_args.mode.lower())
        args.color_mode = mode

    if parsed_args.border is not None:
        border = (BorderStyle)(parsed_args.border.lower())
        args.border_style = border

    return args


def _win_main(args: Arguments) -> None:
    import ansi_win

    driver = ansi_win
    ostate, istate = driver.initialize()

    def signal_trap(sig, frame) -> None:
        '''Ensures terminal state is restored'''
        disable_buffer()
        driver.reset(ostate, istate)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_trap)

    try:
        _main_loop(driver, args)
    except Exception as exception:
        print(exception)
    finally:
        driver.reset(ostate, istate)


def _nix_main(args: Arguments) -> None:
    import ansi_nix

    driver = ansi_nix
    orig_state = driver.initialize()

    def signal_trap(sig, frame) -> None:
        '''Ensures terminal state is restored'''
        disable_buffer()
        driver.reset(orig_state)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_trap)

    try:
        _main_loop(driver, args)
    except Exception as exception:
        print(exception)
    finally:
        driver.reset(orig_state)


def _main_loop(driver: any, args: Arguments) -> None:
    theme = parse_colors(args)

    enable_buffer()
    set_cursor(1, 1)

    # Defaults to 80 columns by 24 lines
    size = shutil.get_terminal_size()
    render_title(size.columns, theme, args.color_mode)
    render_borders(size.columns, size.lines, theme, args)

    f_quit = False  # Flag quit
    while not f_quit:
        key = sys.stdin.read(1)
        if key == driver.KeyCodes.QUIT.value:
            f_quit = True

    disable_buffer()


def parse_colors(args: Arguments) -> Theme:
    cp = configparser.ConfigParser()
    cp.read(args.theme_file)
    mode = args.color_mode.value
    title_color = cp[mode]["title_color"]
    border_color = cp[mode]["border_color"]

    return Theme(
        title_color=title_color,
        border_color=border_color
    )


def enable_buffer() -> None:
    '''Clears the screen'''
    print(f"{CSI}{EN_ALT_BUF}")


def disable_buffer() -> None:
    '''Reverts screen back to
    previous state before script'''
    print(f"{CSI}{DIS_ALT_BUF}")


def set_foreground(color: int, mode: ColorMode) -> None:
    prefix = f"{CSI}38;5;" if mode == ColorMode.Bit8 else f"{CSI};"
    print(f"{prefix}{color}m", end="")


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


def render_title(width: int, theme: Theme, mode: ColorMode) -> None:
    offset = width - (len(TITLE) + 4)
    set_foreground(theme.title_color, mode)
    print(f"{offset * ' '}{TITLE}", end="")
    reset_style()


def render_borders(width: int, height: int, theme: Theme,
                   args: Arguments) -> None:
    x_offset = math.floor(width / 4)
    set_foreground(theme.border_color, args.color_mode)
    if args.border_style == BorderStyle.Single:
        h_border = Border.h_single
        v_border = Border.v_single
        t_border = Border.t_single
    else:
        h_border = Border.h_double
        v_border = Border.v_double
        t_border = Border.t_double

    # Horizontal title separator
    set_cursor(1, 2)
    print(f"{h_border * width}")
    reset_style()

    # Connector
    set_cursor(x_offset, 2)
    print(t_border)

    # Vertical request list separator
    for index in range(height - 3):
        set_cursor(x_offset, index + 3)
        print(v_border)

    # Horizontal request definition
    # and response separator
    x_remain = width - x_offset
    y_half = math.floor((height - 3) / 2)
    set_cursor(x_offset + 1, y_half + 3)
    print(f"{h_border * x_remain}")


if __name__ == "__main__":
    main()

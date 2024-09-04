import sys
import math
import time
import shutil
import signal
import argparse
import threading
import configparser
from enum import Enum
from queue import Queue
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
    active_color: int


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


class Section(Enum):
    List = "list"
    Request = "request"
    Response = "response"


@dataclass
class RenderState:
    theme:  Theme
    args:   Arguments
    size:   tuple[int, int]
    active: Section


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
    hide_cursor()
    bus = Queue()

    update_thread = threading.Thread(target=update_loop,
                                     args=(bus, theme, args),
                                     daemon=True)
    threads = {
        "update_thread": update_thread
        # TODO add request thread
    }
    threads["update_thread"].start()

    f_quit = False  # Flag quit
    while not f_quit:
        key = sys.stdin.read(1)
        match key:
            case driver.KeyCodes.QUIT.value:
                f_quit = True

    show_cursor()
    disable_buffer()


def update_loop(bus: Queue, theme: Theme, args: Arguments) -> None:
    # Defaults to 80 columns by 24 lines
    size = shutil.get_terminal_size()
    state = RenderState(theme, args, size, Section.List)
    render(state)

    while True:
        updateflag = False
        if not bus.empty():
            _ = bus.get()
            # TODO handle messages

        new_size = shutil.get_terminal_size()
        if new_size != state.size:
            state.size = new_size
            updateflag = True

        if updateflag:
            render(state)
        time.sleep(0.1)  # 100 miliseconds


def render(state: RenderState) -> None:
    clear_screen()
    render_title(state)
    render_borders(state)


def parse_colors(args: Arguments) -> Theme:
    cp = configparser.ConfigParser()
    cp.read(args.theme_file)
    mode = args.color_mode.value
    title_color = cp[mode]["title_color"]
    border_color = cp[mode]["border_color"]
    active_color = cp[mode]["active_color"]

    return Theme(
        title_color=title_color,
        border_color=border_color,
        active_color=active_color
    )


def enable_buffer() -> None:
    '''Creates a new screen buffer'''
    print(f"{CSI}{EN_ALT_BUF}")


def disable_buffer() -> None:
    '''Reverts screen back to
    previous state before script'''
    print(f"{CSI}{DIS_ALT_BUF}")


def hide_cursor() -> None:
    print(f"{CSI}?25l")


def show_cursor() -> None:
    print(f"{CSI}?25h")


def clear_screen() -> None:
    print(f"{CSI}2J")


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


def render_title(state: RenderState) -> None:
    set_cursor(1, 1)
    offset = state.size.columns - (len(TITLE) + 4)
    set_foreground(state.theme.title_color, state.args.color_mode)
    print(f"{' ' * offset}{TITLE}")
    reset_style()


def render_borders(state: RenderState) -> None:
    adj_height = state.size.lines - 3  # Account for title
    # List width, req/resp width, req/resp height
    lw, rw, rh = calculate_areas(state.size.columns, adj_height)

    if state.args.border_style == BorderStyle.Single:
        h_border = Border.h_single
        v_border = Border.v_single
        t_border = Border.t_single
    else:
        h_border = Border.h_double
        v_border = Border.v_double
        t_border = Border.t_double

    set_cursor(1, 2)
    set_foreground(
        state.theme.active_color if state.active == Section.List
        else state.theme.border_color,
        state.args.color_mode)
    print(f"{h_border * lw}")

    set_cursor(lw + 1, 2)
    set_foreground(
        state.theme.active_color if state.active == Section.Request
        else state.theme.border_color,
        state.args.color_mode
    )
    print(f"{h_border * rw}", end="")

    set_cursor(lw, 2)
    set_foreground(
        state.theme.active_color if state.active == Section.List
        or state.active == Section.Request
        else state.theme.border_color,
        state.args.color_mode
    )
    print(t_border)

    set_foreground(
        state.theme.active_color if state.active == Section.Request
        or state.active == Section.List
        else state.theme.border_color,
        state.args.color_mode
    )
    for index in range(rh):
        set_cursor(lw, index + 3)
        print(v_border)

    set_foreground(
        state.theme.active_color if state.active == Section.Response
        or state.active == Section.List
        else state.theme.border_color,
        state.args.color_mode
    )
    # Compensate for potential one loss
    comp_height = state.size.lines - rh
    for index in range(comp_height):
        set_cursor(lw, (index + rh))
        print(v_border)

    reset_style()


def calculate_areas(width: int, height: int) -> (int, int, int):
    lw = math.floor(width / 4)   # List width
    rw = width - lw              # Request/Response width
    rh = math.floor(height / 2)  # Request/Response rr_height
    return (lw, rw, rh)


if __name__ == "__main__":
    main()

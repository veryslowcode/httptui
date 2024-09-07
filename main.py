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
from http_parser import HttpRequest, parse_http_file


TITLE = "HTTP/TUI"      # For main application

ESC = "\x1b"            # Escape
CSI = f"{ESC}["         # Control Sequence Introducer

EN_ALT_BUF = "?1049h"   # Enable Alternate Buffer
DIS_ALT_BUF = "?1049l"  # Disable Alternate Buffer


class ColorMode(Enum):
    """
    Indicates the structure of the escape equence
    """
    Bit4 = "4bit"       # Color immediately after CSI
    Bit8 = "8bit"       # Sequence is as follows: 35:5:{color}


@dataclass
class Theme:
    title_color:  int
    border_color: int
    active_color: int
    selected_color: int


@dataclass
class Border:
    t_single = "┬"
    t_double = "╦"
    h_single = "─"
    h_double = "═"
    v_single = "│"
    v_double = "║"
    c_single = "├"
    c_double = "╠"


class BorderStyle(Enum):
    Single = "single"
    Double = "double"


@dataclass
class Arguments:
    file: str = "requests.http"
    theme_file: str = "theme.ini"
    color_mode: ColorMode = ColorMode.Bit8
    border_style: BorderStyle = BorderStyle.Single


class Section(Enum):
    List = 0
    Request = 1
    Response = 2


@dataclass
class ScrollState:
    rlist:    int
    request:  int
    response: int


@dataclass
class RenderState:
    theme:    Theme
    args:     Arguments
    size:     tuple[int, int]
    active:   Section
    selected: int
    requests: list[HttpRequest]
    scroll:   ScrollState
    definition: list[str]


class Message(Enum):
    MoveUp = 0
    MoveDown = 1
    MoveLeft = 2
    MoveRight = 3


def main() -> None:
    """
    Main wraps the platform
    specific implementation
    """
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

    parser.add_argument("-f", "--file",
                        help="Path to requests file " +
                        "(defaults to script 'requests.http')")

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

    if parsed_args.file is not None:
        args.file = parsed_args.file
    else:
        scriptdir = Path(__file__).parent
        args.file = Path(scriptdir, "requests.http")

    return args


def _win_main(args: Arguments) -> None:
    import ansi_win

    driver = ansi_win
    ostate, istate = driver.initialize()

    def signal_trap(sig, frame) -> None:
        """
        Ensures terminal state is restored
        """
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
        """
        Ensures terminal state is restored
        """
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
    """
    Orchestrates all threads of the application.
    Does so by spawning the messages appropriate
    message based on keyboard input and triggering
    the update or request thread.
    """
    theme = parse_colors(args)
    enable_buffer()
    hide_cursor()
    bus = Queue()

    requests = parse_http_file(str(args.file))

    update_thread = threading.Thread(target=update_loop,
                                     args=(bus, theme, args, requests),
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
            case driver.KeyCodes.UP.value:
                bus.put(Message.MoveUp)
            case driver.KeyCodes.DOWN.value:
                bus.put(Message.MoveDown)
            case driver.KeyCodes.LEFT.value:
                bus.put(Message.MoveLeft)
            case driver.KeyCodes.RIGHT.value:
                bus.put(Message.MoveRight)

    show_cursor()
    disable_buffer()


def parse_colors(args: Arguments) -> Theme:
    cp = configparser.ConfigParser()
    cp.read(args.theme_file)
    mode = args.color_mode.value
    title_color = cp[mode]["title_color"]
    border_color = cp[mode]["border_color"]
    active_color = cp[mode]["active_section_color"]
    selected_color = cp[mode]["active_request_color"]

    return Theme(
        title_color=title_color,
        border_color=border_color,
        active_color=active_color,
        selected_color=selected_color
    )


def update_loop(bus: Queue, theme: Theme, args: Arguments,
                requests: list[HttpRequest]) -> None:
    """
    Processes messages produced by the update thread,
    updating render state and triggering a rerender.
    """
    # Defaults to 80 columns by 24 lines
    size = shutil.get_terminal_size()
    scroll_state = ScrollState(0, 0, 0)
    definition = []

    state = RenderState(theme, args, size, Section.List,
                        0, requests, scroll_state, definition)
    if len(requests) > 0:
        state.definition = populate_request_definition(state)

    render(state, True)  # Ensure screen is initially cleared

    while True:
        updateflag = False
        resizeflag = False

        new_size = shutil.get_terminal_size()
        if new_size != state.size:
            # Resize is handled differently
            # with render to avoid flickering
            state.scroll = ScrollState(0, 0, 0)
            state.size = new_size
            updateflag = True
            resizeflag = True

        elif not bus.empty():
            updateflag = True
            message = bus.get()
            match message:
                case Message.MoveUp:
                    if state.active == Section.List:
                        state.selected = update_selected(state, False)
                        state.definition = populate_request_definition(state)
                    else:
                        state = update_scroll(state, False)
                case Message.MoveDown:
                    if state.active == Section.List:
                        state.selected = update_selected(state, True)
                        state.definition = populate_request_definition(state)
                    else:
                        state = update_scroll(state, True)
                case Message.MoveLeft:
                    state.active = update_active(state, False)
                case Message.MoveRight:
                    state.active = update_active(state, True)

        if updateflag:
            render(state, resizeflag)
        time.sleep(0.1)  # 100 miliseconds


def update_active(state: RenderState, increase: bool) -> Section:
    """
    Updates the active section, returning new Section.
    """
    current = state.active.value

    if increase:
        current = state.active.value
        current += 1
        if current > 2:
            current = 0
    else:
        current -= 1
        if current < 0:
            current = 2

    return (Section)(current)


def update_selected(state: RenderState, increase: bool) -> int:
    """
    Updates the selected request, returning index.
    Should only be used when active section is List.
    """
    current = state.selected

    if increase:
        current += 1
        if current >= len(state.requests):
            current = 0
    else:
        current -= 1
        if current < 0:
            current = len(state.requests) - 1

    return current


def update_scroll(state: RenderState, increase: bool) -> RenderState:
    match state.active:
        case Section.List:
            # TODO implement
            pass
        case Section.Request:
            updated = update_scroll_request(state, increase)
            state.scroll.request = updated
            return state
        case Section.Response:
            # TODO implement
            pass

    return state


def update_scroll_request(state: RenderState, increase: bool) -> int:
    """
    Calculates the scroll offset of the Request section,
    increasing/decresing only if the request definition
    is greater than section height.

    Returns an integer representing the request section
    scroll offset.
    """
    y_offset = 3   # Account for title

    adj_height = state.size.lines - y_offset
    middle = math.floor(adj_height / 2)

    max_height = (middle - 1) - y_offset
    scroll = state.scroll.request
    cap = len(state.definition) - 1

    if cap < max_height:
        return scroll

    if increase:
        if scroll <= (cap - max_height):
            scroll += 1
    else:
        if scroll > 0:
            scroll -= 1

    return scroll


def populate_request_definition(state: RenderState) -> list[str]:
    """
    Pre-populate the renderable lines of the selected request
    definition to allow for easy scroll functionality.
    """
    lines = []
    request = state.requests[state.selected]
    lines.append(f"Method -> {request.method.value}")
    lines.append(f"URL -> {request.url}")
    lines.append(f"Encrypted -> {request.encrypted}")
    lines.append("")  # Additional after metadata

    if request.headers:
        lines.append("Headers:")
        for key, value in request.headers.items():
            lines.append(f"{key}: {value}")
        lines.append("")  # Additional separation after headers

    if request.body is not None:
        lines.append("Body:")
        lines.append(request.body)

    return lines


def render(state: RenderState, resize: bool) -> None:
    if resize:
        clear_screen()

    render_title(state)
    render_borders(state)
    render_labels(state)
    render_request_list(state)
    render_request_definition(state)


def render_title(state: RenderState) -> None:
    """
    Renders on the right-hand side of the screen
    """
    x_offset = 1
    y_offset = 1
    padding = 4

    set_cursor(x_offset, y_offset)
    offset = state.size.columns - (len(TITLE) + padding)
    set_foreground(state.theme.title_color, state.args.color_mode)
    print(f"{' ' * offset}{TITLE}")
    reset_style()


def render_borders(state: RenderState) -> None:
    """
    Renders box drawing characters to partition
    sections of the interface, as depicted below:
    Single Border             Double Border
    ─────┬────────────        ═════╦════════════
         │                         ║
         ├────────────             ╠════════════
         │                         ║
    """
    x_offset = math.floor(state.size.columns / 4)
    y_offset = 3   # Account for title
    x_padding = 1  # From the left edge
    adj_height = state.size.lines - y_offset

    if state.args.border_style == BorderStyle.Single:
        h_border = Border.h_single
        v_border = Border.v_single
        t_border = Border.t_single
        c_border = Border.c_single
    else:
        h_border = Border.h_double
        v_border = Border.v_double
        t_border = Border.t_double
        c_border = Border.c_double

    set_foreground(state.theme.border_color, state.args.color_mode)
    set_cursor(x_padding, y_offset - 1)

    print(f"{h_border * state.size.columns}")

    for index in range(adj_height + 1):
        set_cursor(x_offset, index + y_offset)
        print(v_border, end="")

    set_cursor(x_offset, y_offset - 1)
    print(t_border)

    middle = math.floor(adj_height / 2)
    remainder = state.size.columns - x_offset
    set_cursor(x_offset + 1, middle)
    print(f"{h_border * remainder}", end="")

    set_cursor(x_offset, middle)
    print(c_border)

    reset_style()


def render_labels(state: RenderState) -> None:
    """
    Renders the labels associated with the sections:
    List, Request, and Response. Also colors the
    'active' one.
    """
    x_offset = math.floor(state.size.columns / 4)
    y_offset = 3   # Account for title
    x_padding = 2  # From relative left edge
    adj_height = state.size.lines - y_offset
    middle = math.floor(adj_height / 2)

    set_cursor(x_padding, y_offset - 1)
    if state.active == Section.List:
        set_foreground(
            state.theme.active_color,
            state.args.color_mode
        )
    print(" List ")
    reset_style()

    set_cursor(x_offset + x_padding, y_offset - 1)
    if state.active == Section.Request:
        set_foreground(
            state.theme.active_color,
            state.args.color_mode
        )
    print(" Request ")
    reset_style()

    set_cursor(x_offset + x_padding, middle)
    if state.active == Section.Response:
        set_foreground(
            state.theme.active_color,
            state.args.color_mode
        )
    print(" Response ")
    reset_style()


def render_request_list(state: RenderState) -> None:
    max_w = math.floor(state.size.columns / 4) - 1
    requests = state.requests
    x_offset = 2
    y_offset = 3

    set_cursor(x_offset, y_offset)
    for i in range(len(requests)):
        if state.active == Section.List and state.selected == i:
            set_foreground(state.theme.selected_color, state.args.color_mode)

        request = requests[i]
        name = request.name if request.name != "" else request.url
        if len(name) > max_w:
            name = name[:max_w - 2]  # Length of ..
            name = name + ".."
        print(name)

        reset_style()
        set_cursor(x_offset, (y_offset + i) + 1)


def render_request_definition(state: RenderState) -> None:
    x_offset = math.floor(state.size.columns / 4)
    y_offset = 3   # Account for title
    x_padding = 2  # From relative left edge
    x_offset += x_padding
    adj_height = state.size.lines - y_offset
    middle = math.floor(adj_height / 2)
    max_height = (middle - 1) - y_offset

    for index in range((middle - 1) - y_offset):
        set_cursor(x_offset, y_offset + index)
        clear_line_from_cursor()

    definition = state.definition
    scroll = state.scroll.request

    if len(definition) >= max_height:
        for row in range(max_height):
            set_cursor(x_offset, y_offset)
            y_offset = render_incrementing_y(
                    x_offset, y_offset, definition[row + scroll])
    else:
        set_cursor(x_offset, y_offset)
        for line in state.definition:
            y_offset = render_incrementing_y(
                    x_offset, y_offset, line)


def render_incrementing_y(x_offset: int, y_offset: int, output: str) -> int:
    set_cursor(x_offset, y_offset)
    print(output)
    return y_offset + 1


def enable_buffer() -> None:
    """
    Creates a new screen buffer
    """
    print(f"{CSI}{EN_ALT_BUF}")


def disable_buffer() -> None:
    """
    Reverts screen back to
    previous state before script
    """
    print(f"{CSI}{DIS_ALT_BUF}")


def hide_cursor() -> None:
    print(f"{CSI}?25l")


def show_cursor() -> None:
    print(f"{CSI}?25h")


def clear_screen() -> None:
    print(f"{CSI}2J")


def clear_line_from_cursor() -> None:
    print(f"{CSI}0K")


def set_foreground(color: int, mode: ColorMode) -> None:
    prefix = f"{CSI}38;5;" if mode == ColorMode.Bit8 else f"{CSI};"
    print(f"{prefix}{color}m", end="")


def reset_style() -> None:
    print(f"{CSI}0m", end="")


def set_cursor(x: int, y: int) -> None:
    """
    Escape sequence to move the
    cursor with the assumption that
    location (1,1) is at the top
    left of the screen.

    It also assumes that {x} and {y}
    are based on character size.
    """
    print(f'{CSI}{y};{x}H', end="")


if __name__ == "__main__":
    main()

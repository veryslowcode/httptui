import sys
import math
import time
import shutil
import signal
import requests
import argparse
import traceback
import threading
import configparser
from enum import Enum
from queue import Queue
from pathlib import Path
from dataclasses import dataclass
from req_struct import HttpBodyType
from http_parser import HttpRequest, parse_http_file


TITLE = "HTTP/TUI"      # For main application

ESC = "\x1b"            # Escape
CSI = f"{ESC}["         # Control Sequence Introducer

EN_ALT_BUF = "?1049h"   # Enable Alternate Buffer
DIS_ALT_BUF = "?1049l"  # Disable Alternate Buffer

X_OFFSET = 2            # From left edge
X_PADDING = 2           # From relative left edge
Y_OFFSET = 3            # Accounts for title row and separator row


class ColorMode(Enum):
    """
    Indicates the structure of the escape equence
    """
    Bit4 = "4bit"       # Color immediately after CSI
    Bit8 = "8bit"       # Sequence is as follows: 35:5:{color}


@dataclass
class Theme:
    text_color:   int
    title_color:  int
    border_color: int
    active_color: int
    selected_color: int


@dataclass
class Border:
    h_single = "─"
    h_double = "═"
    v_single = "│"
    v_double = "║"
    ltc_single = "┌"
    ltc_double = "╔"
    ltc_rounded = "╭"
    lbc_single = "└"
    lbc_double = "╚"
    lbc_rounded = "╰"
    rtc_single = "┐"
    rtc_double = "╗"
    rtc_rounded = "╮"
    rbc_single = "┘"
    rbc_double = "╝"
    rbc_rounded = "╯"


class BorderStyle(Enum):
    Single = "single"
    Double = "double"
    Rounded = "rounded"


@dataclass
class Arguments:
    debug: bool = False
    file: str = "requests.http"
    theme_file: str = "theme.ini"
    color_mode: ColorMode = ColorMode.Bit8
    border_style: BorderStyle = BorderStyle.Rounded


class Section(Enum):
    List = 0
    Request = 1
    Response = 2


@dataclass
class AwaitState:
    animation: int = 0
    waiting:   bool = False


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
    borders:  dict
    response: list[str]
    definition: list[str]
    await_request: AwaitState


class Message(Enum):
    MoveUp = 0
    MoveDown = 1
    MoveLeft = 2
    MoveRight = 3
    AwaitRequest = 4
    ResponseReceived = 5


global_exception: Exception = None
global_request: HttpRequest = None
global_response: str = None


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

    parser.add_argument("-g", "--debug", action="store_true",
                        help=argparse.SUPPRESS)

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

    args.debug = parsed_args.debug

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
        if global_exception is not None:
            print(global_exception)
            traceback.print_tb(global_exception.__traceback__)
        sys.exit(1)


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
        if global_exception is not None:
            print(global_exception)
            traceback.print_tb(global_exception.__traceback__)
        sys.exit(1)


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

    global global_request
    global_request = requests[0]

    update_thread = threading.Thread(target=update_loop,
                                     args=(bus, theme, args, requests),
                                     daemon=True)
    threads = {
        "update_thread": update_thread,
    }
    threads["update_thread"].start()

    f_quit = False  # Flag quit
    while not f_quit and threads["update_thread"].is_alive():
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
            case driver.KeyCodes.SPACE.value:
                bus.put(Message.AwaitRequest)
                threads["request_thread"] = threading.Thread(
                    target=send_request,
                    args=(global_request, bus),
                    daemon=True
                )
                threads["request_thread"].start()
        sys.stdin.flush()

    show_cursor()
    disable_buffer()


def parse_colors(args: Arguments) -> Theme:
    cp = configparser.ConfigParser()
    cp.read(args.theme_file)
    mode = args.color_mode.value
    text_color = cp[mode]["text_color"]
    title_color = cp[mode]["title_color"]
    border_color = cp[mode]["border_color"]
    active_color = cp[mode]["active_section_color"]
    selected_color = cp[mode]["active_request_color"]

    return Theme(
        text_color=text_color,
        title_color=title_color,
        border_color=border_color,
        active_color=active_color,
        selected_color=selected_color
    )


def update_loop(bus: Queue, theme: Theme, args: Arguments,
                requests: list[HttpRequest]) -> None:
    """
    Simple wrapper to ensure global exception is
    set, if needed, from the update thread.
    """
    try:
        _update_loop(bus, theme, args, requests)
    except Exception as exception:
        clear_screen()

        set_cursor(2, 2)
        set_foreground(theme.text_color, args.color_mode)
        print("An unexpected exception occured")

        set_cursor(2, 3)
        print("Press any key to continue")

        global global_exception
        global_exception = exception
        sys.exit(1)


def _update_loop(bus: Queue, theme: Theme, args: Arguments,
                 requests: list[HttpRequest]) -> None:
    """
    Processes messages produced by the update thread,
    updating render state and triggering a rerender.
    """
    # Defaults to 80 columns by 24 lines
    size = shutil.get_terminal_size()
    scroll_state = ScrollState(0, 0, 0)
    borders = populate_borders(args)
    await_state = AwaitState()
    definition = []
    response = []

    state = RenderState(theme, args, size, Section.List, 0, requests,
                        scroll_state, borders, response,
                        definition, await_state)

    if len(requests) > 0:
        state.definition = populate_request_definition(state)

    render(state, True)  # Ensure screen is initially cleared

    while True:
        updateflag = False
        resizeflag = False
        animateflag = False

        new_size = shutil.get_terminal_size()
        if new_size != state.size:
            # Resize is handled differently
            # with render to avoid flickering
            state.scroll = ScrollState(0, 0, 0)
            state.size = new_size
            updateflag = True
            resizeflag = True

        elif not bus.empty():
            message = bus.get()
            state, updateflag = handle_bus_event(message, state)
        elif state.await_request.waiting:
            state.await_request.animation = update_request_animation(state)
            animateflag = True
            time.sleep(0.2)

        if updateflag:
            render(state, resizeflag)
        elif animateflag:
            render_await_request(state)


def handle_bus_event(message: Message, state: RenderState
                     ) -> (RenderState, bool):
    global global_request
    if not state.await_request.waiting:
        updateflag = True
        match message:
            case Message.MoveUp:
                if state.active == Section.List:
                    state.response = []
                    state.selected = update_selected(state, False)
                    state.definition = populate_request_definition(state)
                    global_request = state.requests[state.selected]
                state = update_scroll(state, False)
            case Message.MoveDown:
                if state.active == Section.List:
                    state.response = []
                    state.selected = update_selected(state, True)
                    state.definition = populate_request_definition(state)
                    global_request = state.requests[state.selected]
                state = update_scroll(state, True)
            case Message.MoveLeft:
                state.active = update_active(state, False)
            case Message.MoveRight:
                state.active = update_active(state, True)
            case Message.AwaitRequest:
                state.response = []
                state.await_request.waiting = True
    else:
        match message:
            case Message.ResponseReceived:
                global global_response
                state.response = populate_response(global_response)
                state.await_request.waiting = False
                updateflag = True

    return (state, updateflag)


def populate_response(response: requests.Response) -> list[str]:
    """
    Given a response object, this parses the content
    and creates an array of that content for the
    application to use for rendering.
    """
    content = []
    content.append(f"Status code -> {global_response.status_code} " +
                   f"{response.reason}")
    content.append("")
    content.append("Headers:")
    for key, value in response.headers.items():
        content.append(f"{key}: {value}")
    content.append("")
    if response.text != "":
        content += response.text.split("\n")

    return content


def populate_borders(args: Arguments) -> dict:
    borders = {}
    if args.border_style == BorderStyle.Single:
        borders["h_border"] = Border.h_single
        borders["v_border"] = Border.v_single
        borders["lt_corner"] = Border.ltc_single
        borders["lb_corner"] = Border.lbc_single
        borders["rt_corner"] = Border.rtc_single
        borders["rb_corner"] = Border.rbc_single
    elif args.border_style == BorderStyle.Rounded:
        borders["h_border"] = Border.h_single
        borders["v_border"] = Border.v_single
        borders["lt_corner"] = Border.ltc_rounded
        borders["lb_corner"] = Border.lbc_rounded
        borders["rt_corner"] = Border.rtc_rounded
        borders["rb_corner"] = Border.rbc_rounded
    else:
        borders["h_border"] = Border.h_double
        borders["v_border"] = Border.v_double
        borders["lt_corner"] = Border.ltc_double
        borders["lb_corner"] = Border.lbc_double
        borders["rt_corner"] = Border.rtc_double
        borders["rb_corner"] = Border.rbc_double
    return borders


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
        if current < len(state.requests) - 1:
            current += 1
    else:
        if current > 0:
            current -= 1

    return current


def update_scroll(state: RenderState, increase: bool) -> RenderState:
    match state.active:
        case Section.List:
            state.scroll.request = 0
            state.scroll.response = 0
            updated = update_scroll_list(state, increase)
            state.scroll.rlist = updated
        case Section.Request:
            updated = update_scroll_request(state, increase)
            state.scroll.request = updated
        case Section.Response:
            updated = update_scroll_response(state, increase)
            state.scroll.response = updated

    return state


def update_scroll_list(state: RenderState, increase: bool) -> int:
    """
    Calculates the scroll offset of the List section,
    increasing/decresing only if the amount of requests
    is greater than the section height.

    Returns an integer representing the request section
    scroll offset.
    """
    padding = 3
    adj_height = state.size.lines - Y_OFFSET - padding

    if len(state.requests) < adj_height:
        return state.scroll.rlist

    scroll = state.scroll.rlist
    if increase:
        if scroll < (len(state.requests) - adj_height) \
                and state.selected >= adj_height:
            scroll += 1
    else:
        if scroll > 0 and state.selected - scroll < 0:
            scroll -= 1

    return scroll


def update_scroll_request(state: RenderState, increase: bool) -> int:
    """
    Calculates the scroll offset of the Request section,
    increasing/decresing only if the request definition
    is greater than the section height.

    Returns an integer representing the request section
    scroll offset.
    """
    height = math.floor((state.size.lines - X_PADDING) / 2)
    adj_height = height - Y_OFFSET - 1
    scroll = state.scroll.request

    if len(state.definition) < adj_height:
        return scroll

    if increase:
        if scroll < len(state.definition) - adj_height:
            scroll += 1
    elif scroll > 0:
        scroll -= 1

    return scroll


def update_scroll_response(state: RenderState, increase: bool) -> int:
    """
    Calculates the scroll offset of the Response section,
    increasing/decresing only if the response is greater
    than the section height.

    Returns an integer representing the response section
    scroll offset.
    """
    height = math.floor((state.size.lines - X_PADDING) / 2)
    adjustment = 2
    adj_height = height - adjustment
    scroll = state.scroll.response

    if len(state.response) < adj_height:
        return scroll

    if increase:
        if scroll < len(state.response) - adj_height:
            scroll += 1
    elif scroll > 0:
        scroll -= 1

    return scroll


def update_request_animation(state: RenderState) -> int:
    update = state.await_request.animation + 1
    if update >= 5:
        update = 0
    return update


def populate_request_definition(state: RenderState) -> list[str]:
    """
    Pre-populate the renderable lines of the selected request
    definition to allow for easy scroll functionality.
    """
    lines = []
    request = state.requests[state.selected]
    lines.append(f"Method -> {request.method.value}")
    lines.append(f"URL -> {request.url}")
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

    render_header(state)
    render_list(state)
    render_request(state)
    render_response(state)
    print("")

    if state.args.debug:
        _render_debug(state)


def render_header(state: RenderState) -> None:
    """
    Renders the top bar containing the title
    and styles appropriately.
    ╭───────────────────────╮
    │                Title  │
    ╰───────────────────────╯
    """
    width = state.size.columns - 2
    height = 3
    edge = 1

    top, bottom = get_top_bottom_borders(state, width)
    middle = f"{' ' * (width - (len(TITLE) + X_PADDING))}{TITLE}"

    set_foreground(state.theme.border_color, state.args.color_mode)

    set_cursor(edge, edge)
    print(top, end="")
    set_cursor(edge, height - 1)
    print(state.borders["v_border"], end="")

    set_foreground(state.theme.title_color, state.args.color_mode)
    print(middle)
    set_foreground(state.theme.border_color, state.args.color_mode)

    set_cursor(width + X_PADDING, height - 1)
    print(state.borders["v_border"], end="")
    set_cursor(edge, height)
    print(bottom, end="")
    reset_style()


def render_list(state: RenderState) -> None:
    """
    Renders the request list section of the
    interface and styles appropriately.
    ╭─ List ────╮
    │ Url       │
    │ Url       │
    │ Url       │
    │ ...       │
    ╰───────────╯
    """
    offset = 2  # Account for gap and top border
    height = state.size.lines - 1
    width = math.floor(state.size.columns / 4)
    top, bottom = get_top_bottom_borders(state, width)

    set_cursor(X_OFFSET - 1, Y_OFFSET + 1)
    color = state.theme.active_color    \
        if state.active == Section.List \
        else state.theme.border_color

    set_foreground(color, state.args.color_mode)
    print(top, end="")

    set_cursor(X_OFFSET + 1, Y_OFFSET + 1)
    set_foreground(state.theme.text_color, state.args.color_mode)
    print(" List ", end="")
    set_foreground(color, state.args.color_mode)

    for index in range(height - Y_OFFSET - offset):
        set_cursor(X_OFFSET - 1, Y_OFFSET + index + offset)

        if (len(state.requests) > index):
            request = state.requests[index + state.scroll.rlist]
            name = request.name if request.name != "" else request.url
            name = name.replace("\n", "").replace("\r", "")
            name = cap_line_width(width, name)
            line = f"{name}{' ' * (width - len(name))}"
        else:
            line = ' ' * width

        print(f"{state.borders['v_border']}", end="")

        if state.selected == index + state.scroll.rlist:
            set_foreground(state.theme.selected_color, state.args.color_mode)
            print(line, end="")
            set_foreground(color, state.args.color_mode)
        else:
            set_foreground(state.theme.text_color, state.args.color_mode)
            print(line, end="")
            set_foreground(color, state.args.color_mode)

        set_cursor(width + X_OFFSET, Y_OFFSET + index + offset)
        print(f"{state.borders['v_border']}", end="")

    set_cursor(X_OFFSET - 1, height)
    print(bottom, end="")
    reset_style()


def render_request(state: RenderState) -> None:
    """
    Renders the request definition section of the
    interface and styles appropriately.
    ╭─ Request ──────────╮
    │ Method -> GET      │
    │ URL -> example.com │
    │ ...                │
    ╰────────────────────╯
    """
    height = math.floor((state.size.lines - X_PADDING) / 2)

    offset = 2
    padding = X_PADDING * 2
    quarter = math.floor(state.size.columns / 4)
    width = state.size.columns - (quarter + (padding + 1))

    top, bottom = get_top_bottom_borders(state, width)

    color = state.theme.active_color       \
        if state.active == Section.Request \
        else state.theme.border_color

    set_cursor(quarter + padding, Y_OFFSET + 1)
    set_foreground(color, state.args.color_mode)
    print(top, end="")

    set_cursor(quarter + padding + offset, Y_OFFSET + 1)
    set_foreground(state.theme.text_color, state.args.color_mode)
    print(" Request ", end="")
    set_foreground(color, state.args.color_mode)
    scroll = state.scroll.request

    for index in range(height - Y_OFFSET - 1):
        line = f"{state.borders['v_border']}"
        if len(state.definition) > index:
            row = state.definition[index + scroll]
            row = cap_line_width(width, str(row))
            line += get_foreground(state.theme.text_color,
                                   state.args.color_mode)
            line += f"{row}{' ' * (width - len(row))}"
            line += get_foreground(color, state.args.color_mode)
        else:
            line += " " * (width)
        line += state.borders["v_border"]
        set_cursor(quarter + padding, Y_OFFSET + index + offset)
        print(line, end="")

    set_cursor(quarter + padding, height + 1)
    print(bottom, end="")


def render_response(state: RenderState) -> None:
    """
    Renders the response definition section of the
    interface and styles appropriately.
    ╭─ Response ─────────╮
    │ Status Code 200    │
    │ ...                │
    │                    │
    ╰────────────────────╯
    """
    height = math.floor((state.size.lines - X_PADDING) / 2)

    offset = 2
    padding = X_PADDING * 2
    quarter = math.floor(state.size.columns / 4)
    width = state.size.columns - (quarter + (padding + 1))

    top, bottom = get_top_bottom_borders(state, width)

    color = state.theme.active_color        \
        if state.active == Section.Response \
        else state.theme.border_color

    set_cursor(quarter + padding, height + 2)
    set_foreground(color, state.args.color_mode)
    print(top, end="")

    set_cursor(quarter + padding + offset, height + 2)
    set_foreground(state.theme.text_color, state.args.color_mode)
    print(" Response ", end="")
    set_foreground(color, state.args.color_mode)
    scroll = state.scroll.response

    for index in range(height - 2):
        line = f"{state.borders['v_border']}"
        response = state.response
        if response is not None and len(response) > index:
            row = response[index + scroll]
            row = cap_line_width(width, str(row))
            line += get_foreground(state.theme.text_color,
                                   state.args.color_mode)
            line += f"{row}{' ' * (width - len(row))}"
            line += get_foreground(color, state.args.color_mode)
        else:
            line += " " * (width)
        line += state.borders["v_border"]
        set_cursor(quarter + padding, height + index + offset + 1)
        print(line, end="")

    set_cursor(quarter + padding, (height * 2) + 1)
    print(bottom, end="")


def render_await_request(state: RenderState) -> None:
    quarter = math.floor(state.size.columns / 4)
    height = math.floor((state.size.lines - X_PADDING) / 2)
    middle = math.floor(state.size.columns / 2) + math.floor(quarter / 2)

    x_pos = middle
    y_pos = height + math.floor(height / 2)

    set_cursor(x_pos, y_pos)
    small = "·"
    large = "•"

    normal = state.theme.text_color
    active = state.theme.selected_color

    line = ""
    set_foreground(normal, state.args.color_mode)

    for i in range(5):
        if i == state.await_request.animation:
            line += get_foreground(active, state.args.color_mode)
            line += large
            line += get_foreground(normal, state.args.color_mode)
        else:
            line += small

    print(line)


def get_top_bottom_borders(state: RenderState, width: int) -> (str, str):
    top = f"{state.borders['lt_corner']}" +        \
          f"{state.borders['h_border'] * width}" + \
          f"{state.borders['rt_corner']}"

    bottom = f"{state.borders['lb_corner']}" +        \
             f"{state.borders['h_border'] * width}" + \
             f"{state.borders['rb_corner']}"

    return (top, bottom)


def cap_line_width(max_w: int, line: str) -> str:
    if len(str(line)) > max_w:
        capped = str(line)[:max_w - 2]  # Length of ..
        capped = capped + ".."
        line = capped
    return line


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
    print(f"{CSI}2J", end="")


def clear_line_from_cursor() -> None:
    print(f"{CSI}0K")


def set_foreground(color: int, mode: ColorMode) -> None:
    prefix = f"{CSI}38;5;" if mode == ColorMode.Bit8 else f"{CSI};"
    print(f"{prefix}{color}m", end="")


def get_foreground(color: int, mode: ColorMode) -> str:
    prefix = f"{CSI}38;5;" if mode == ColorMode.Bit8 else f"{CSI};"
    return f"{prefix}{color}m"


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


def _render_debug(state: RenderState) -> None:
    debug = \
        f"wid {state.size.columns} hgt {state.size.lines} | " + \
        f"act {state.active.value} | sel {state.selected} | " + \
        f"lislen {len(state.requests)} | " +                    \
        f"scr {state.scroll.rlist} {state.scroll.request} " +   \
        f"{state.scroll.response} | " +                         \
        f"deflen {len(state.definition)} | " +                  \
        f"reslen {len(state.response)}"

    pos_y = state.size.lines - 1
    pos_x = state.size.columns - len(debug) - 2

    set_cursor(pos_x - 5, pos_y)
    clear_line_from_cursor()

    set_cursor(pos_x, pos_y)
    print(debug)


def send_request(request: HttpRequest, bus: Queue) -> None:
    json = None
    data = None
    file = None
    if request.body is not None:
        match request.body.body_type:
            case HttpBodyType.textplain:
                data = request.body.body
            case HttpBodyType.xwwwformurlencoded:
                data = request.body.body
            case HttpBodyType.json:
                json = request.body.body
            case HttpBodyType.multipartformdata:
                file = request.body.body
        response = requests.request(request.method.value.upper(),
                                    request.url,
                                    headers=request.headers,
                                    json=json,
                                    data=data,
                                    files=file)
    else:
        response = requests.request(request.method.value.upper(),
                                    request.url,
                                    headers=request.headers)
    global global_response
    global_response = response
    bus.put(Message.ResponseReceived)


if __name__ == "__main__":
    main()

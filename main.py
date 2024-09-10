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
from req_struct import HttpBodyType
from dataclasses import dataclass, field
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
    # ColorMode {{{
    Bit4 = "4bit"       # Color immediately after CSI
    Bit8 = "8bit"       # Sequence is as follows: 35:5:{color}
    Bit24 = "24bit"     # RGB color sequence
    # }}}


@dataclass
class Theme:
    # Theme {{{
    text_color:   int
    title_color:  int
    border_color: int
    active_color: int
    selected_color: int
    # }}}


@dataclass
class Border:
    # Border {{{
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
    # }}}


class BorderStyle(Enum):
    # BorderStyle {{{
    Single = "single"
    Double = "double"
    Rounded = "rounded"
    # }}}


@dataclass
class Arguments:
    # Arguments {{{
    debug: bool = False
    file: str = "requests.http"
    theme_file: str = "theme.ini"
    color_mode: ColorMode = ColorMode.Bit24
    border_style: BorderStyle = BorderStyle.Rounded
    # }}}


class Section(Enum):
    # Section {{{
    List = 0
    Request = 1
    Response = 2
    # }}}


class Expanded(Enum):
    # Expanded {{{
    Main = 0
    Request = 1
    Response = 2
    # }}}


@dataclass
class AwaitState:
    # AwaitState {{{
    animation: int = 0
    error:     str = None
    waiting:   bool = False
    response:  requests.Response = None
    # }}}


@dataclass
class ScrollState:
    # ScrollState {{{
    rlist:    int
    request:  int
    response: int
    # }}}


@dataclass
class RenderState:
    # RenderState {{{
    borders: dict
    theme:   Theme
    args:    Arguments
    size:    tuple[int, int]
    requests: list[HttpRequest]

    selected:   int = 0
    active:     Section = Section.List
    expanded:   Expanded = Expanded.Main
    response:   list[str] = field(default_factory=list)
    definition: list[str] = field(default_factory=list)

    scroll: ScrollState = field(
        default_factory=lambda: ScrollState(0, 0, 0)
    )

    await_request: AwaitState = field(
        default_factory=lambda: AwaitState()
    )
    # }}}


class Message(Enum):
    # Message {{{
    MoveUp = 0
    MoveDown = 1
    MoveLeft = 2
    MoveRight = 3
    Expand = 4
    AwaitRequest = 5
    ResponseReceived = 6
    ResponseErrored = 7
    # }}}


# Globals, be cautious with use
global_exception: Exception = None
global_request:   HttpRequest = None
global_response:  requests.Response = None
global_response_error: requests.RequestException = None


def main() -> None:
    """
    Main wraps the platform
    specific implementation
    """
    # main {{{
    args = parse_args()
    if sys.platform == "win32":
        _win_main(args)
    else:
        _nix_main(args)
    # }}}


def _main_loop(driver: any, args: Arguments) -> None:
    """
    Orchestrates all threads of the application.
    Does so by spawning the messages appropriate
    message based on keyboard input and triggering
    the update or request thread.
    """
    # _main_loop {{{
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

            case driver.KeyCodes.EXPAND.value:
                bus.put(Message.Expand)

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
    # }}}


def _win_main(args: Arguments) -> None:
    # _win_main {{{
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
    # }}}


def _nix_main(args: Arguments) -> None:
    # _nix_main {{{
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
    # }}}


def _render_debug(state: RenderState) -> None:
    # _render_debug {{{
    width, height = calculate_rr_size(state)

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
    # }}}


def _send_request(request: HttpRequest, bus: Queue) -> None:
    # _send_request {{{
    global global_response
    file = None
    data = None
    djson = None

    if request.body is None:
        response = requests.request(
            request.method.value.upper(),
            request.url, headers=request.headers)
    else:
        match request.body.body_type:
            case HttpBodyType.textplain:
                data = request.body.body
            case HttpBodyType.xwwwformurlencoded:
                data = request.body.body
            case HttpBodyType.json:
                djson = request.body.body
            case HttpBodyType.multipartformdata:
                file = request.body.body

        response = requests.request(
            request.method.value.upper(), request.url,
            headers=request.headers, json=djson,
            data=data, files=file)

    global_response = response
    bus.put(Message.ResponseReceived)
    # }}}


def _update_loop(bus: Queue, theme: Theme, args: Arguments,
                 requests: list[HttpRequest]) -> None:
    """
    Processes messages produced by the update thread,
    updating render state and triggering a rerender.
    """
    # _update_loop {{{
    # Defaults to 80 columns by 24 lines
    size = shutil.get_terminal_size()
    borders = populate_borders(args)

    state = RenderState(
        borders=borders, theme=theme, args=args,
        size=size, requests=requests
    )

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

            state.definition = populate_request_definition(state)

            if state.await_request.response is not None:
                state.response = populate_response(
                        state.await_request.response, state)
            elif state.await_request.error is not None:
                error = state.await_request.error
                state.response = populate_response_error(error, state)

        elif not bus.empty():
            message = bus.get()
            state, updateflag, resizeflag = handle_bus_event(message, state)

        elif state.await_request.waiting:
            state.await_request.animation = update_request_animation(state)
            animateflag = True
            time.sleep(0.2)  # 200 miliseconds

        if updateflag:
            render(state, resizeflag)
        elif animateflag:
            render_await_request(state)
    # }}}


def break_line_width(max_w: int, line: str) -> list[str]:
    """
    This breaks a line into a list of strings based on
    a provided width, indenting the broken peices.
    """
    # break_line_width {{{
    line = str(line)
    if len(line) < max_w:
        return [line]

    offset = 0
    result = []
    result.append(line[:max_w])

    indent = "  "
    sample = line[max_w:]
    for index in range(math.floor(len(sample) / (max_w + 2))):
        result.append(f"{indent}{sample[offset:offset + max_w - len(indent)]}")
        offset += max_w - len(indent)

    if len(line) % (max_w + 2) != 0:
        result.append(f"{indent}{sample[offset:]}")

    return result
    # }}}


def calculate_rr_offset(state: RenderState) -> (int, int):
    """
    Returns the x_offset and y_offset for the request/response
    sections, accounting for expanded state.
    """
    # calculate_rr_offset {{{
    if state.expanded == Expanded.Main:
        return (4, 2)
    else:
        return (2, 4)
    # }}}


def calculate_rr_size(state: RenderState) -> (int, int):
    """
    Returns the width and height for the request/response
    sections, accounting for expanded state.
    """
    # calculate_rr_size {{{
    if state.expanded == Expanded.Main:
        quarter = math.floor(state.size.columns / 4)
        width = state.size.columns - 1 - quarter
        height = height = math.floor(state.size.lines / 2) - 1
    else:
        width = state.size.columns - 2
        height = state.size.lines - 1
    return (width, height)
    # }}}


def cap_line_width(max_w: int, line: str) -> str:
    """
    Cuts a line short, appending with ..
    to indicate this
    """
    # cap_line_width {{{
    if len(str(line)) > max_w:
        capped = str(line)[:max_w - 2]  # Length of ..
        capped = capped + ".."

        line = capped
    return line
    # }}}


def clear_screen() -> None:
    # clear_screen {{{
    print(f"{CSI}2J", end="")
    # }}}


def clear_line_from_cursor() -> None:
    # clear_line_from_cursor {{{
    print(f"{CSI}0K")
    # }}}


def disable_buffer() -> None:
    """
    Reverts screen back to
    previous state before script
    """
    # disable_buffer {{{
    print(f"{CSI}{DIS_ALT_BUF}")
    # }}}


def enable_buffer() -> None:
    """
    Creates a new screen buffer
    """
    # enable_buffer {{{
    print(f"{CSI}{EN_ALT_BUF}")
    # }}}


def get_foreground(color: str, mode: ColorMode) -> str:
    # get_foreground {{{
    match mode:
        case ColorMode.Bit4:
            prefix = f"{CSI}"
            return f"{prefix}{color}m"
        case ColorMode.Bit8:
            prefix = f"{CSI}38;5;"
            return f"{prefix}{color}m"
        case ColorMode.Bit24:
            r, g, b = color.split(",")
            prefix = f"{CSI}38;2;"
            return f"{prefix}{r};{g};{b}m"
    # }}}


def get_top_bottom_borders(state: RenderState, width: int) -> (str, str):
    # get_top_bottom_borders {{{
    top = f"{state.borders['lt_corner']}" +        \
          f"{state.borders['h_border'] * width}" + \
          f"{state.borders['rt_corner']}"

    bottom = f"{state.borders['lb_corner']}" +        \
             f"{state.borders['h_border'] * width}" + \
             f"{state.borders['rb_corner']}"

    return (top, bottom)
    # }}}


def handle_bus_event(message: Message, state: RenderState
                     ) -> (RenderState, bool, bool):
    """
    Makes the necessary calls upon receiving a
    message from the bus, returning the updated
    state and an updateflag value.
    """
    # handle_bus_event {{{
    global global_request
    resizeflag = False
    updateflag = False
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
                if state.expanded == Expanded.Main:
                    state.active = update_active(state, False)
                else:
                    updateflag = False

            case Message.MoveRight:
                if state.expanded == Expanded.Main:
                    state.active = update_active(state, True)
                else:
                    updateflag = False

            case Message.Expand:
                if state.expanded != Expanded.Main:
                    state.scroll.request = 0
                    state.scroll.response = 0
                    state.expanded = Expanded.Main
                elif state.active == Section.Request:
                    state.scroll.request = 0
                    state.scroll.response = 0
                    state.expanded = Expanded.Request
                elif state.active == Section.Response:
                    state.scroll.request = 0
                    state.scroll.response = 0
                    state.expanded = Expanded.Response
                else:
                    return (state, False, False)

                state.definition = populate_request_definition(state)

                if state.await_request.response is not None:
                    state.response = populate_response(
                        state.await_request.response, state)
                elif state.await_request.error is not None:
                    error = state.await_request.error
                    state.response = populate_response_error(error, state)

                resizeflag = True

            case Message.AwaitRequest:
                if state.expanded != Expanded.Main:
                    return (state, False, False)
                else:
                    state.response = []
                    state.await_request.error = None
                    state.await_request.waiting = True
                    state.await_request.response = None

    else:
        match message:
            case Message.ResponseReceived:
                global global_response
                state.response = populate_response(global_response, state)
                state.await_request.response = global_response
                state.await_request.waiting = False
                updateflag = True

            case Message.ResponseErrored:
                global global_response_error
                state.await_request.error = str(global_response_error)
                state.response = populate_response_error(
                        str(global_response_error), state)
                state.await_request.waiting = False
                updateflag = True

    return (state, updateflag, resizeflag)
    # }}}


def hide_cursor() -> None:
    # hide_cursor {{{
    print(f"{CSI}?25l")
    # }}}


def parse_args() -> Arguments:
    # parse_args {{{
    description = "Send and recieve HTTP request in the terminal"
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("-t", "--theme",
                        help="Path to theme file " +
                        "(defaults to 'theme.ini')")

    parser.add_argument("-m", "--mode",
                        help="Color style: '4bit', '8bit', or '24bit' " +
                        "(defaults to '24bit')")

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
    # }}}


def parse_colors(args: Arguments) -> Theme:
    # parse_colors {{{
    cp = configparser.ConfigParser()
    cp.read(args.theme_file)
    mode = args.color_mode.value

    text_color = validate_colors(
        "text_color", cp[mode]["text_color"],
        args.color_mode
    )
    title_color = validate_colors(
        "title_color", cp[mode]["title_color"],
        args.color_mode
    )
    border_color = validate_colors(
        "border_color", cp[mode]["border_color"],
        args.color_mode
    )
    active_color = validate_colors(
        "active_section_color", cp[mode]["active_section_color"],
        args.color_mode
    )
    selected_color = validate_colors(
        "active_request_color", cp[mode]["active_request_color"],
        args.color_mode
    )

    return Theme(
        text_color=text_color,
        title_color=title_color,
        border_color=border_color,
        active_color=active_color,
        selected_color=selected_color
    )
    # }}}


def populate_borders(args: Arguments) -> dict:
    # populate_borders {{{
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
    # }}}


def populate_response(response: requests.Response,
                      state: RenderState) -> list[str]:
    """
    Given a response object, this parses the content
    and creates an array of that content for the
    application to use for rendering.
    """
    # populate_response {{{
    offset, _ = calculate_rr_offset(state)
    width, _ = calculate_rr_size(state)
    width = width - offset

    content = []
    content.append(f"Status code -> {response.status_code} " +
                   f"{response.reason}")
    content += break_line_width(width, f"URL -> {response.url}")
    content.append("")
    content.append("Headers:")
    for key, value in response.headers.items():
        line = f"{key}: {value}"
        lines = break_line_width(width, line)
        content += lines

    if response.text != "":
        content.append("")  # Additional separation after headers
        content.append("Body:")
        for line in response.text.splitlines():
            content += break_line_width(width, line)

    return content
    # }}}


def populate_request_definition(state: RenderState) -> list[str]:
    """
    Pre-populate the renderable lines of the selected request
    definition to allow for easy scroll functionality.
    """
    # populate_request_definition {{{
    width, _ = calculate_rr_size(state)
    offset, _ = calculate_rr_offset(state)
    width = width - offset

    lines = []
    request = state.requests[state.selected]
    lines.append(f"Method -> {request.method.value}")
    lines += break_line_width(width, f"URL -> {request.url}")
    lines.append("")  # Additional after metadata

    if request.headers:
        lines.append("Headers:")
        for key, value in request.headers.items():
            lines += break_line_width(width, f"{key}: {value}")

    if request.body is not None:
        lines.append("")  # Additional separation after headers
        lines.append("Body:")
        lines += break_line_width(width, request.body.body)

    return lines
    # }}}


def populate_response_error(error: str, state: RenderState) -> list[str]:
    # populate_response_error {{{
    offset, _ = calculate_rr_offset(state)
    width, _ = calculate_rr_size(state)
    width = width - offset

    content = []
    for line in error.splitlines():
        content += break_line_width(width, line)

    return content
    # }}}


def render(state: RenderState, resize: bool) -> None:
    """
    Main render function
    """
    # render {{{
    if resize:
        clear_screen()

    render_header(state)
    match state.expanded:
        case Expanded.Main:
            render_list(state)
            render_request(state)
            render_response(state)
        case Expanded.Request:
            render_request(state)
        case Expanded.Response:
            render_response(state)
    print("")

    if state.args.debug:
        _render_debug(state)
    # }}}


def render_await_request(state: RenderState) -> None:
    """
    Renders the loading animation in the response
    section of the interface.
    ╭─ Response ─────────╮
    │                    │
    │       ··•··        │
    │                    │
    ╰────────────────────╯
    """
    # render_await_request {{{
    width, height = calculate_rr_size(state)
    x_offset, y_offset = calculate_rr_size(state)
    width += x_offset

    scalar_x = math.floor(math.floor(state.size.columns / 4) / 2)

    x_middle = math.floor(width / 2) - scalar_x
    y_middle = math.floor(height + y_offset / 2)

    set_cursor(x_middle, y_middle)
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
    # }}}


def render_header(state: RenderState) -> None:
    """
    Renders the top bar containing the title
    and styles appropriately.
    ╭───────────────────────╮
    │                Title  │
    ╰───────────────────────╯
    """
    # render_header {{{
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
    # }}}


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
    # render_list {{{
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
    # }}}


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
    # render_response {{{
    width, height = calculate_rr_size(state)
    x_offset, y_offset = calculate_rr_offset(state)

    top, bottom = get_top_bottom_borders(state, width - x_offset)
    scroll = state.scroll.response

    color = state.theme.active_color        \
        if state.active == Section.Response \
        else state.theme.border_color

    if state.expanded == Expanded.Main:
        scalar_x = math.floor(state.size.columns / 4)
        scalar_y = height
    else:
        scalar_x = 0
        scalar_y = 0

    set_foreground(color, state.args.color_mode)
    set_cursor(scalar_x + x_offset, scalar_y + y_offset)
    print(top, end="")

    # Magic 2 represents offset for section title
    set_cursor(scalar_x + x_offset + 2, scalar_y + y_offset)
    set_foreground(state.theme.text_color, state.args.color_mode)
    print(" Response ", end="")

    set_foreground(color, state.args.color_mode)
    for index in range(height - y_offset):
        line = f"{state.borders['v_border']}"
        response = state.response
        if response is not None and len(response) > (index + scroll):
            row = response[index + scroll]
            row = cap_line_width(width - x_offset, str(row))
            line += get_foreground(state.theme.text_color,
                                   state.args.color_mode)
            line += f"{row}{' ' * (width - x_offset - len(row))}"
            line += get_foreground(color, state.args.color_mode)
        else:
            line += " " * (width - x_offset)

        line += state.borders["v_border"]
        set_cursor(scalar_x + x_offset,
                   scalar_y + index + y_offset + 1)

        print(line, end="")

    if state.expanded == Expanded.Main:
        # Magic 1 is to account for math.floor
        set_cursor(scalar_x + x_offset,
                   scalar_y + height + 1)
    else:
        set_cursor(x_offset, height)
    print(bottom, end="")
    # }}}


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
    # render_request {{{
    width, height = calculate_rr_size(state)
    x_offset, y_offset = calculate_rr_offset(state)

    top, bottom = get_top_bottom_borders(state, width - x_offset)
    scroll = state.scroll.request

    color = state.theme.active_color        \
        if state.active == Section.Request  \
        else state.theme.border_color

    if state.expanded == Expanded.Main:
        scalar_x = math.floor(state.size.columns / 4)
        scalar_y = 2
    else:
        scalar_x = 0
        scalar_y = 0

    set_foreground(color, state.args.color_mode)
    set_cursor(scalar_x + x_offset, scalar_y + y_offset)
    print(top, end="")

    # Magic 2 represents offset for section title
    set_cursor(scalar_x + x_offset + 2, scalar_y + y_offset)
    set_foreground(state.theme.text_color, state.args.color_mode)
    print(" Response ", end="")

    set_foreground(color, state.args.color_mode)
    for index in range(height - y_offset):
        line = f"{state.borders['v_border']}"
        definition = state.definition
        if definition is not None and len(definition) > (index + scroll):
            row = definition[index + scroll]
            row = cap_line_width(width - x_offset, str(row))
            line += get_foreground(state.theme.text_color,
                                   state.args.color_mode)
            line += f"{row}{' ' * (width - x_offset - len(row))}"
            line += get_foreground(color, state.args.color_mode)
        else:
            line += " " * (width - x_offset)

        line += state.borders["v_border"]
        set_cursor(scalar_x + x_offset,
                   scalar_y + index + y_offset + 1)

        print(line, end="")

    if state.expanded == Expanded.Main:
        # Magic 1 is to account for math.floor
        set_cursor(scalar_x + x_offset,
                   scalar_y + height - 1)
    else:
        set_cursor(x_offset, height)

    print(bottom, end="")
    # }}}


def reset_style() -> None:
    # reset_style {{{
    print(f"{CSI}0m", end="")
    # }}}


def send_request(request: HttpRequest, bus: Queue) -> None:
    """
    Primary function that comprises the request thread.
    Wraps implementation try/expect.
    """
    # send_request {{{
    try:
        _send_request(request, bus)
    except Exception as exception:
        global global_response_error
        global_response_error = exception
        bus.put(Message.ResponseErrored)
    # }}}


def set_cursor(x: int, y: int) -> None:
    """
    Escape sequence to move the
    cursor with the assumption that
    location (1,1) is at the top
    left of the screen.

    It also assumes that {x} and {y}
    are based on character size.
    """
    # set_cursor {{{
    print(f'{CSI}{y};{x}H', end="")
    # }}}


def set_foreground(color: str, mode: ColorMode) -> None:
    # set_foreground {{{
    match mode:
        case ColorMode.Bit4:
            prefix = f"{CSI}"
            print(f"{prefix}{color}m", end="")
        case ColorMode.Bit8:
            prefix = f"{CSI}38;5;"
            print(f"{prefix}{color}m", end="")
        case ColorMode.Bit24:
            r, g, b = color.split(",")
            prefix = f"{CSI}38;2;"
            print(f"{prefix}{r};{g};{b}m", end="")
    # }}}


def show_cursor() -> None:
    # show_cursor {{{
    print(f"{CSI}?25h")
    # }}}


def update_active(state: RenderState, increase: bool) -> Section:
    """
    Updates the active section, returning new Section.
    """
    # update_active {{{
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
    # }}}


def update_loop(bus: Queue, theme: Theme, args: Arguments,
                requests: list[HttpRequest]) -> None:
    """
    Simple wrapper to ensure global exception is
    set, if needed, from the update thread.
    """
    # update_loop {{{
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
    # }}}


def update_request_animation(state: RenderState) -> int:
    # update_request_animation {{{
    update = state.await_request.animation + 1
    if update >= 5:
        update = 0
    return update
    # }}}


def update_scroll(state: RenderState, increase: bool) -> RenderState:
    # update_scroll {{{
    match state.active:
        case Section.List:
            state.scroll.request = 0
            state.scroll.response = 0
            updated = update_scroll_list(state, increase)
            state.scroll.rlist = updated

        case Section.Request:
            updated = update_scroll_rr(state, increase)
            state.scroll.request = updated

        case Section.Response:
            updated = update_scroll_rr(state, increase)
            state.scroll.response = updated

    return state
    # }}}


def update_scroll_list(state: RenderState, increase: bool) -> int:
    """
    Calculates the scroll offset of the List section,
    increasing/decresing only if the amount of requests
    is greater than the section height.

    Returns an integer representing the request section
    scroll offset.
    """
    # update_scroll_list {{{
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
    # }}}


def update_scroll_rr(state: RenderState, increase: bool) -> int:
    """
    Calculates the scroll offset of the request/response section,
    increasing/decresing only if the request definition
    is greater than the section height.

    Returns an integer representing the offset.
    """
    # update_scroll_rr {{{
    _, height = calculate_rr_size(state)
    _, offset = calculate_rr_offset(state)
    height = height - offset

    section = state.active
    if section == Section.Request:
        scroll = state.scroll.request
        length = len(state.definition)
    else:
        scroll = state.scroll.response
        length = len(state.response)

    if length < height:
        return scroll

    scalar_y = 0
    if state.expanded == Expanded.Main:
        if state.active == Section.Response:
            scalar_y = -1
        else:
            scalar_y = 1

    if increase:
        if scroll <= length - (height - scalar_y):
            scroll += 1
    elif scroll > 0:
        scroll -= 1

    return scroll
    # }}}


def update_selected(state: RenderState, increase: bool) -> int:
    """
    Updates the selected request, returning index.
    Should only be used when active section is List.
    """
    # update_selected {{{
    current = state.selected

    if increase:
        if current < len(state.requests) - 1:
            current += 1
    else:
        if current > 0:
            current -= 1

    return current
    # }}}


def validate_colors(key: str, color: str, mode: ColorMode) -> str:
    """
    We may be expecting an integer value or an array depending
    on the color mode. This validates the expected format.
    """
    # validate_colors {{{
    if mode == ColorMode.Bit24:
        split = color.split(",")
        if len(split) != 3:
            raise Exception(f"Invalid RGB color format for {key}={color}")
        else:
            return color
    else:
        try:
            int(color)
            return color
        except Exception:
            raise Exception(f"Color must be an integer for {key}={color}")
    # }}}


if __name__ == "__main__":
    main()

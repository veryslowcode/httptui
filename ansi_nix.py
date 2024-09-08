from enum import Enum
import tty
import sys
import termios


class KeyCodes(Enum):
    ENTER = "\x0D"
    QUIT = "\x11"
    UP = "k"
    DOWN = "j"
    LEFT = "h"
    RIGHT = "l"


def initialize() -> list:
    '''
    This setup function is relavent on unix-like
    systems to ensure the escape codes passed to
    the terminal operate as expected. It returns
    the original state of the terminal,
    applicable to the reset_unix function.
    '''
    fileno = sys.stdin.fileno()
    state = termios.tcgetattr(fileno)
    tty.setraw(fileno)
    return state


def reset(original_state: list) -> None:
    '''
    This is required because some terminals on unix-like systems
    will not return, by default, to their original state. This
    function is used to address this.
    '''
    fileno = sys.stdin.fileno()
    termios.tcsetattr(fileno, termios.TCSADRAIN, original_state)

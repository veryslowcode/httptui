from ctypes.wintypes import DWORD
from enum import Enum
import ctypes


class KeyCodes(Enum):
    QUIT = "\x11"
    UP = "k"
    DOWN = "j"
    LEFT = "h"
    RIGHT = "l"


# Input Constants
STD_INPUT_HANDLE = -10
ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200

# Output Constants
STD_OUTPUT_HANDLE = -11
ENABLE_PROCESSED_OUTPUT = 0x0001
ENABLE_WRAP_AT_EOL_OUTPUT = 0x0002
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def initialize() -> (ctypes.c_long, ctypes.c_long):
    '''
    In certain environments, this function may not
    be needed, such as running PowerShell in Windows
    Terminal. In other situations, such as running
    Windows CMD 'straight', this allows the escape
    characters to function properly.

    Returns (output, input)
    '''
    kernel = ctypes.windll.kernel32
    stdin = kernel.GetStdHandle(STD_INPUT_HANDLE)
    stdout = kernel.GetStdHandle(STD_OUTPUT_HANDLE)
    istate = DWORD()
    ostate = DWORD()
    kernel.GetConsoleMode(stdin, ctypes.byref(istate))
    kernel.GetConsoleMode(stdout, ctypes.byref(ostate))
    kernel.SetConsoleMode(
            stdin,
            ENABLE_VIRTUAL_TERMINAL_INPUT
    )
    kernel.SetConsoleMode(
            stdout,
            ENABLE_PROCESSED_OUTPUT |
            ENABLE_WRAP_AT_EOL_OUTPUT |
            ENABLE_VIRTUAL_TERMINAL_PROCESSING
    )
    return (ostate, istate)


def reset(ostate: ctypes.c_long, istate: ctypes.c_long) -> None:
    '''
    Though not strictly necessary, this function is used as a
    means to ensure the user's terminal is returned to the
    way it was before using this application.
    '''
    kernel = ctypes.windll.kernel32
    stdin = kernel.GetStdHandle(STD_INPUT_HANDLE)
    stdout = kernel.GetStdHandle(STD_OUTPUT_HANDLE)
    kernel.SetConsoleMode(stdin, istate)
    kernel.SetConsoleMode(stdout, ostate)

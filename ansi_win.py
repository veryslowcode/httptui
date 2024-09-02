from ctypes.wintypes import DWORD
from enum import Enum
import ctypes


class KeyCodes(Enum):
    QUIT = ""  # TODO discover


# Windows specific constants
STD_OUTPUT_HANDLE = -11
ENABLE_PROCESSED_OUTPUT = 0x0001
ENABLE_WRAP_AT_EOL_OUTPUT = 0x0002
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def initialize() -> ctypes.c_long:
    '''
    In certain environments, this function may not
    be needed, such as running PowerShell in Windows
    Terminal. In other situations, such as running
    Windows CMD 'straight', this allows the escape
    characters to function properly.
    '''
    kernel = ctypes.windll.kernel32
    stdout = kernel.GetStdHandle(STD_OUTPUT_HANDLE)
    state = DWORD()
    kernel.GetConsoleMode(stdout, ctypes.byref(state))
    kernel.SetConsoleMode(
            stdout,
            ENABLE_PROCESSED_OUTPUT |
            ENABLE_WRAP_AT_EOL_OUTPUT |
            ENABLE_VIRTUAL_TERMINAL_PROCESSING
    )
    return state


def reset(original_state: ctypes.c_long) -> None:
    '''
    Though not strictly necessary, this function is used as a
    means to ensure the user's terminal is returned to the
    way it was before using this application.
    '''
    kernel = ctypes.windll.kernel32
    stdout = kernel.GetStdHandle(STD_OUTPUT_HANDLE)
    kernel.SetConsoleMode(stdout, original_state)

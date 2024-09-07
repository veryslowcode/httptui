# HTTP/TUI

TUI application for storing and sending HTTP requests.

## Usage

```sh
usage: main.py [-h] [-t THEME] [-m MODE] [-b BORDER] [-f FILE]

Send and recieve HTTP request in the terminal

options:
  -h, --help            show this help message and exit
  -t THEME, --theme THEME
                        Path to theme file (defaults to 'theme.ini')
  -m MODE, --mode MODE  Color style: '4bit' or '8bit' (defaults to '8bit')
  -b BORDER, --border BORDER
                        Border style: 'single' or 'double' (defaults to 'single')
  -f FILE, --file FILE  Path to requests file (defaults to script 'requests.http')
```

## File Format

This application follows a `.http` file format almost the same
as the one described in the following
[Microsoft Documentation](https://learn.microsoft.com/en-us/aspnet/core/test/http-files?view=aspnetcore-8.0)

The primary difference is this application supports the ability
to assign a name to a given request (for display in the UI)
using the `&` character.

```sh
[HTTP Method] [URL] [HTTP Version]
[Header Key]: [Header Value]
...

[Request Body]
```

Use the following conventions within the `.http` file
```sh
# or //  For Comments
&        For request name

[@name=value] For variable definition
{{name}}      For variable usage
```

>[!NOTE]
>Variables must be defined before a request
>and names (optional) must be defined before
> a request, but after variables.

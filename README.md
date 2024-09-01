# HTTP/TUI

TUI application for storing and sending HTTP requests.

## File Format

`.http` file format as described from the following 
[Microsoft Documentation](https://learn.microsoft.com/en-us/aspnet/core/test/http-files?view=aspnetcore-8.0)

```ps1
[HTTP Method] [URL] [HTTP Version]
[Header Key]: [Header Value]
...

[Request Body]
```

Use the following conventions within the `.http` file
```ps1
# or //  For Comments

[@name=value] For variable definition
{{name}}      For variable usage
```

>[!NOTE]
>Variables must be defined before a request

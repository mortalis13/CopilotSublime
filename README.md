Integration of **GitHub Copilot** into **Sublime Text**

### Installation

- Copy the plugin to the Sublime Text `Packages` folder
- Create `.copilot_token` inside the plugin folder and place a GitHub Copilot token in it
  - A token would have prefix `ghu_`
  - It could be retrieved using:
    - **VS Code**: after logging in with the GitHub Copilot account, check the file `AppData\Local\github-copilot\apps.json` (Windows) -> property `oauth_token`
    - **OpenCode**: `~/.local/share/opencode/auth.json` -> `refresh`
    - **Pi**: `~/.pi/agent/auth.json` -> `refresh`
- Ensure the **Package Control** is installed (used to install additional Python libraries needed for the plugin)
- Restart Sublime Text
- Package Control should inform about the libraries installation
- Restart again
- Check the Sublime Text console for errors

### Usage

Two main shortcuts are provided:
- `Ctrl + Shift + I` - to get a response, in an empty view or with a context from an existing text
- `Ctrl + I` - to create code

Examples:
- Create a new tab, type a request, and press `Ctrl + Shift + I` to get a response in the same view
  - After the response, type the next request to chain the conversation
- Use `Ctrl + Shift + I` in an existing file to get a context response, with or without a selection
- Use `Ctrl + I` to create code, the current file text is used as context, including the selected text

### Config

- To change the model, modify `MODEL` inside `copilot_api.py` (restart Sublime Text after any modification)
- The plugin uses predefined AI system rules, depending on the context, which can be modified in the `template.py` (restart Sublime Text)
- Check `Default.sublime-keymap` for the commands and shortcuts configuration

### Notes
- The request input panels save history, but only for the current editor session
- The conversation command `Ctrl + Shift + I` detects the type of conversation (new or with context) by the view syntax, among other criteria
- Use `Ctrl + Alt + Shift + V` to paste text as plain text, without syntax, so it can be used in a new conversation
- The waiting for response loader is in the status bar
- The plugin stores logs with all the requests and responses (raw and formatted)

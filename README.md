**Sublime Text** plugin for AI assistance integration

### Supported Providers and Models

- Antrhopic Claude
- OpenAI
- Google Gemini
- GitHub Copilot
- JetBrains AI (+ proxies for Claude, OpenAI, Gemini)

### Installation

- Copy the plugin to the Sublime Text `Packages` folder
- Ensure the **Package Control** is installed (used to install additional Python libraries needed for the plugin)
- Restart Sublime Text
- Package Control should inform about the libraries installation
- Restart again
- Check the Sublime Text console for errors
- Copy `Copilot.sublime-settings` to `Packages/User`
- Set the `token` property to a token/API key of a provider
- Set the `model` property to a provider model or use the `Copilot: Select Model` command to select a model from the provider API

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

The config file is `Packages/User/Copilot.sublime-settings`

- To use **GitHub Copilot** models
  - Use `gh-` prefix in the `model`
  - Set `token`
    - It would have prefix `ghu_`
    - It could be retrieved using:
      - **VS Code**: after logging in with the GitHub Copilot account, check the file `AppData\Local\github-copilot\apps.json` (Windows) -> property `oauth_token`
      - **OpenCode**: `~/.local/share/opencode/auth.json` -> `refresh`
      - **Pi**: `~/.pi/agent/auth.json` -> `refresh`

- To use **JetBrains AI** models
  - Use `jb-` prefix in the `model`
  - Set `token`
    - Can be extracted using a proxy listener, like **mitmproxy**, and checking for an authentication HTTP call when using chat inside a JetBrains IDE
    - It should have JWT format, and can be found in the `Authorization` header
  - Set `jetbrains_license` to the JetBrains subscription license ID, which can be retrieved from the JetBrains account page

- To use a **proxy** (currently only *JetBrains AI* proxy is supported, with connections to Claude, OpenAI and Gemini API)
  - Set `proxy` to `true`
  - For JetBrains proxy, set `jetbrains_license` to the JetBrains subscription license ID, which can be retrieved from the JetBrains account page
  - Set a `model`
    - It should match a model of the corresponding provider
    - Or it can be selected from a dynamic list with the `Copilot: Select Model` command

- Use optional `url` property to set a custom provider API URL

- The plugin uses predefined AI system rules, depending on the context, which can be modified in the `template.py` (restart Sublime Text)
- Check `Default.sublime-keymap` for the commands and shortcuts configuration

### Notes
- The request input panels save history, but only for the current editor session
- The conversation command `Ctrl + Shift + I` detects the type of conversation (new or with context) by the view syntax, among other criteria
- Use `Ctrl + Alt + Shift + V` to paste text as plain text, without syntax, so it can be used in a new conversation
- The waiting for response loader is in the status bar
- The plugin stores logs with all the requests and responses (raw and formatted)

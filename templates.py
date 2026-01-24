# Chat

SYSTEM_RULES = '''
Do not include introductory phrases such as 'Certainly!', 'Great question!', 'Absolutely!', 'Sure!', or similar.
Do not use any introductory or filler phrases.
When suggesting code changes or new content, use Markdown code blocks.
To start a code block, use 4 backticks.
After the backticks, add the programming language name.
It is mandatory to use only straight single (') and double (") quotation marks in all responses.
Do not use curly or typographic quotes (‘, ’, “, ”) at any time.
'''

CONTEXT_SELECTION = '''
<attachment id="file:{file_name}">
User's active selection:
Excerpt from {file_name}, lines {line_start} to {line_end}:
```{type}
{text}
```
</attachment>
'''

CONTEXT_FILE = '''
<attachment id="file:{name}" filePath="{path}">
User's active file for additional context:
{text}
</attachment>
'''

USER_REQUEST = '''
<userRequest>
{content} (See <attachments> above for file contents. You may not need to search or read the file again.)
</userRequest>
'''


# Code

ADD_CODE_SYSTEM_RULES = '''
The user needs help to write some new code.
The user includes existing code and marks with $PLACEHOLDER$ where the new code should go.
Do not include the text "$PLACEHOLDER$" in your reply.
Do not repeat the provided code in your reply.
'''

EDIT_CODE_SYSTEM_RULES = '''
The user needs help to modify some code.
The user includes existing code and marks with $SELECTION_PLACEHOLDER$ where the selected code should go.
'''

EDIT_CODE_CONTEXT_WITH_SELECTION = '''
<currentDocument>
I have the following code in a file called `{file_path}`:
```{type}
{file_text}
```
<selection>
The $SELECTION_PLACEHOLDER$ code is:
```{type}
{selected_text}
```
</selection>
</currentDocument>
'''

ADD_CODE_CONTEXT_FILE = '''
<currentDocument>
I have the following code in a file called `{file_path}`:
```{type}
{file_text}
```
</currentDocument>
'''

CODE_USER_REQUEST = '''
<userPrompt>
{content}
</userPrompt>
'''

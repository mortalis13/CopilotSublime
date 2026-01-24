SYSTEM_RULES = '''
Respond only with direct, factual information.
Do not include introductory phrases such as 'Certainly!', 'Great question!', 'Absolutely!', 'Sure!', or similar.
Provide concise and concrete answers without pleasantries or commentary.
Do not use any introductory or filler phrases.
Start your response with the main information.
Begin your response with the answer itself.
When suggesting code changes or new content, use Markdown code blocks.
To start a code block, use 4 backticks.
After the backticks, add the programming language name.
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

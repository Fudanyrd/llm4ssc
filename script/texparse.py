import os, sys, re, io
from enum import Enum

_empty_list = []

class NodeBase():
    __slots__ = ['children']
    def __init__(self, children: list):
        self.children: list[NodeBase] = children

    def recurse(self, action):
        action(self)
        for child in self.children:
            child.recurse(action)

    def fmt(self, buf: io.TextIOBase | io.TextIOWrapper):
        """Format the content in compact form, without extra line breaks or indentation."""
        for child in self.children:
            child.fmt(buf)


class TextNode(NodeBase):
    __slots__ = ['word'] # a 'token' which contains no whitespaces.
    def __init__(self, word: str):
        super().__init__([]) # no children
        self.word = word

    def fmt(self, buf: io.TextIOBase | io.TextIOWrapper):
        buf.write(self.word)

    def __repr__(self):
        return self.word

    def is_linebreak(self):
        return self.word == '\n'

    def is_comment(self):
        return self.word.startswith('%')
    
    def is_manual_linebreak(self):
        return self.word in ['\\\\', '\\newline', '\\linebreak']

class CommandNode(NodeBase):
    r"""
    Represents a LaTex command, e.g.
    ```tex
    \includegraphics[width=2cm]{a.png}
    %               ^ optarg   ^arg
    ```
    """
    __slots__ = ['opt_args', 'args', 'name', 'is_numbered']
    section_cmds = ['section', 'subsection', 'subsubsection', 'chapter']
    paragraph_cmds = ['paragraph', 'subparagraph']
    def __init__(self, name, args: list[NodeBase], opt_args: list[NodeBase], is_numbered: bool = True):
        super().__init__([]) # no children
        self.args = args
        self.opt_args = opt_args 
        self.name = name
        self.is_numbered = is_numbered

    def is_paragraph_cmd(self):
        return self.name in self.paragraph_cmds

    def is_section_cmd(self):
        return self.name in self.section_cmds

    def fmt(self, buf: io.TextIOBase | io.TextIOWrapper):
        buf.write('\\' + self.name)
        for opt_arg in self.opt_args:
            buf.write('[')
            opt_arg.fmt(buf)
            buf.write(']')
        for arg in self.args:
            buf.write('{')
            arg.fmt(buf)
            buf.write('}')

class ParagraphNode(NodeBase):
    """Represents a paragraph."""
    __slots__ = []
    def __init__(self, children: list[NodeBase]):
        super().__init__(children)


class SectionNode(NodeBase):
    class SectionKind(Enum):
        TOP = 0
        CHAPTER = 1
        SECTION = 2
        SUBSECTION = 3
        SUBSUBSECTION = 4

    __slots__ = ['kind', 'name_node', 'is_numbered']
    def __init__(self, kind: SectionKind, name_node: NodeBase, is_numbered: bool, children: list[NodeBase]):
        super().__init__(children)
        self.kind = kind
        self.name_node = name_node
        self.is_numbered = is_numbered

    def fmt(self, buf: io.TextIOBase | io.TextIOWrapper):
        if self.kind == self.SectionKind.CHAPTER:
            buf.write('\\chapter')
        elif self.kind == self.SectionKind.SECTION:
            buf.write('\\section')
        elif self.kind == self.SectionKind.SUBSECTION:
            buf.write('\\subsection')
        elif self.kind == self.SectionKind.SUBSUBSECTION:
            buf.write('\\subsubsection')
        else:
            raise ValueError('Invalid section kind.')

        if not self.is_numbered:
            buf.write('*')
        buf.write('{')
        self.name_node.fmt(buf)
        buf.write('}')
        for child in self.children:
            child.fmt(buf)


class EnvironNode(NodeBase):
    """Represents an environment, e.g.
    ```tex
    \begin{figure}
        ...
    \end{figure}
    ```
    """
    __slots__ = ['name', 'is_numbered', 'args', 'opt_args']
    NO_AUTOBREAK_ENVIRONS = set([
        # source code
        'minted',
        'lstlisting',
    ])
    # in these environs, line break '\n' is the same as blank.
    LINE_TO_BLANK_ENVIRONS = {
        'tabular',
    }
    def __init__(self, name: str, children: list[NodeBase], 
                 args: list[NodeBase],
                 optional_args: list[NodeBase],
                 is_numbered: bool = True):
        super().__init__(children)
        self.name = name
        self.args = args
        self.opt_args = optional_args
        self.is_numbered = is_numbered

    def dump_name(self):
        return self.name + ('*' if not self.is_numbered else '')

    def fmt(self, buf: io.TextIOBase | io.TextIOWrapper):
        buf.write(f'\\begin{{{self.dump_name()}}}')
        for arg in self.args:
            buf.write('{')
            arg.fmt(buf)
            buf.write('}')
        for opt_arg in self.opt_args:
            buf.write('[')
            opt_arg.fmt(buf)
            buf.write(']')
        for child in self.children:
            child.fmt(buf)
        buf.write(f'\\end{{{self.dump_name()}}}')

    @staticmethod
    def _check_and_append(children: list[NodeBase], child: ParagraphNode):
        isblank=True
        for ch in child.children:
            if not isinstance(ch, TextNode): 
                isblank=False
                break
            if ch.word != ' ':
                isblank=False
                break

        if not isblank:
            children.append(child)

    def split_by_paragraphs(self):
        """
        After the first phase of parsing, this node
        looks like a stream of words; calling this
        method will split them into several paragraphs, i.e.
        group the children into ParagraphNodes.
        """
        if self.name in self.NO_AUTOBREAK_ENVIRONS:
            return # do not split these environments, for better formatting.
        if self.name in self.LINE_TO_BLANK_ENVIRONS:
            for i, child in enumerate(self.children):
                if isinstance(child, TextNode) and child.is_linebreak():
                    self.children[i] = TextNode(' ')
            return

        splits: list[NodeBase] = []
        cur_para:NodeBase = ParagraphNode([])
        linebreak: bool = False

        nc = len(self.children)
        i = 0
        while i < nc:
            nlb = False
            child = self.children[i]
            if isinstance(child, TextNode):
                if child.is_linebreak():
                    if linebreak:
                        # two adjacent line break: new paragraph.
                        self._check_and_append(splits, cur_para)
                        cur_para = ParagraphNode([])
                    else:
                        cur_para.children.append(TextNode(' ')) # treat line break as space, for better formatting.
                    nlb = True
                else:
                    cur_para.children.append(child)
            elif isinstance(child, TextBlockNode):
                cur_para.children.append(child)
            elif isinstance(child, CommandNode):
                if child.is_paragraph_cmd():
                    # paragraph command: split here.
                    self._check_and_append(splits, cur_para)
                    cur_para = ParagraphNode([child])
                elif child.is_section_cmd():
                    # section command: split here, and also start a new paragraph.
                    self._check_and_append(splits, cur_para)
                    cur_para = ParagraphNode([])
                    splits.append(child)
                else:
                    cur_para.children.append(child)
            elif isinstance(child, EnvironNode):
                # treat environment as a special kind of paragraph.
                self._check_and_append(splits, cur_para)
                cur_para = ParagraphNode([])
                splits.append(child)
            else:
                raise ValueError('Invalid node type in split_by_paragraphs.')

            i += 1
            linebreak = nlb
        if cur_para.children:
            splits.append(cur_para)

        if len(splits) == 1 and isinstance(splits[0], ParagraphNode):
            self.children = splits[0].children
        else:
            self.children = splits

class TopLevelNode(NodeBase):
    __slots__ = []
    def __init__(self, predef: NodeBase, # everything before `\begin{document}`
                 document: NodeBase): # the `document` environment
        super().__init__([predef, document])


class TokenizeBase():
    def next(self) -> str | None:
        raise NotImplemented


class FileTokenizer(TokenizeBase):
    argument_seq = ['[', ']', '{', '}', '$']
    whitespaces = [' ', '\t']
    def __init__(self, pth: str):
        self.fobj = open(pth, 'r', encoding='utf-8')
        self._curline  = '' # current line
        self._idx = 0

    def __del__(self):
        self.fobj.close()

    def _refill(self) -> None:
        self._curline = self.fobj.readline()
        self._curline = self._curline.replace('\r\n', '\n')
        self._idx = 0

    def next(self):
        if self._idx >= len(self._curline):
            self._refill()
        if self._idx >= len(self._curline):
            return None

        ll = len(self._curline)
        # skip whitespaces
        start = self._idx
        if self._curline[self._idx] in self.whitespaces:
            while self._curline[self._idx] in self.whitespaces:
                self._idx += 1
            return self._curline[start: self._idx]

        if self._curline[self._idx]  == '\n':
            self._idx += 1
            return '\n' # parser needs this to separate paragraphs.

        if self._curline[self._idx]  == '%':
            ret = self._curline[self._idx:]
            self._idx = ll
            return ret

        if self._curline [self._idx] in self.argument_seq:
            ret = self._curline[self._idx]
            self._idx += 1;
            if ret == '$' and self._curline[self._idx] == '$':
                raise ValueError("plainTex style $$ math mode is not supported, use \\[...\\] instead.")
            return ret

        if self._curline[self._idx] == '\\':
            self._idx += 1
            if not self._curline[self._idx].isalpha():
                self._idx += 1
                return self._curline[start: self._idx] # e.g. \\ 
        while self._curline[self._idx] not in (self.argument_seq + self.whitespaces + ['\n', '%', '\\']):
            self._idx += 1
        return self._curline[start:self._idx]

class TextBlockNode(NodeBase):
    """
    Represents a block of text wrapped in curly braces.
    """
    __slots__ = []
    def __init__(self, children):
        super().__init__(children)
    

class Parser():
    matcher = {
        '{': '}',
        '[': ']',
        '$': '$', # inline math mode
    }
    def __init__(self, tokenizer: TokenizeBase):
        self.pending_tokens = []
        self.tokenizer = tokenizer
    
    @staticmethod
    def _is_comment(tok: str):
        return tok and tok.startswith('%')

    def _next(self):
        if self.pending_tokens:
            # unused by previous looking-ahead.
            ret = self.pending_tokens[0]
            del self.pending_tokens[0]
            return ret
        tok = self.tokenizer.next()
        if not self._is_comment(tok):
            return tok
        
        # concatenate adjacent comment tokens into one, for better formatting later.
        comment_str = tok.replace('\n', ' ')
        while True:
            tok = self.tokenizer.next()
            if tok is None:
                break
            elif self._is_comment(tok):
                comment_str += tok[1:].replace('\n', ' ') # skip the leading '%'
            elif tok == '\n':
                comment_str += ' '
            elif tok.isspace():
                comment_str += ' '
            else:
                self.pending_tokens.append(tok)
                break
        return comment_str + '\n'


    def match_brace(self, node: NodeBase, cur: str):
        while True:
            tok = self._next()
            if tok is None:
                break
            if tok == self.matcher[cur]:
                break
            if tok in self.matcher:
                # nested brace, recursively match it.
                new_node = TextBlockNode([])
                self.match_brace(new_node, tok)
                node.children.append(new_node)
            else:
                node.children.append(TextNode(tok))

    def fill_command(self, cmd: CommandNode, first_token: str):
        assert first_token.startswith('\\')
        if first_token.endswith('*'):
            cmd.is_numbered=False
            cmd.name = first_token[1:-1]
        else:
            cmd.name = first_token[1:]
        while True:
            tok = self._next()
            if tok is None:
                break
            if tok == '[': # optional argument
                optarg = NodeBase([])
                self.match_brace(optarg, tok)
                cmd.opt_args.append(optarg)
            elif tok == '{': # mandatory argument
                arg = NodeBase([])
                self.match_brace(arg, tok)
                cmd.args.append(arg)
            # elif tok == '\n' or tok == ' ': continue
            else:
                self.pending_tokens.append(tok)
                break

    @staticmethod
    def _is_identifier_start(ch: str):
        return ch.isalpha() or ch == '_';

    @staticmethod
    def _env_end(tok: str):
        return tok.startswith('\\end')

    @staticmethod
    def _text_block_end(tok: str):
        return tok == '}'

    def fill_environ(self, env: EnvironNode):
        """Continue parsing environ's optional argument(s) until token is not '['"""
        while True:
            tok = self._next()
            if tok is None:
                break
            if tok == '[': # optional argument
                optarg = NodeBase([])
                self.match_brace(optarg, tok)
                env.opt_args.append(optarg)
            elif tok == '{': # mandatory argument
                arg = NodeBase([])
                self.match_brace(arg, tok)
                env.args.append(arg)
            # elif tok == '\n' or tok == ' ': continue
            else:
                self.pending_tokens.append(tok)
                break

    def parse_till(self, parent: NodeBase, predicate):
        while True:
            tok = self._next()
            if tok is None or predicate(tok):
                break

            # handle different type of tokens here.
            if tok.startswith('\\begin'):
                # handle environment.
                assert self._next() == '{'
                name = self._next()
                assert name is not None
                assert self._next() == '}'
                env = EnvironNode(name, [], [], [])
                self.fill_environ(env)
                self.parse_till(env, self._env_end)
                parent.children.append(env)
                for _ in range(3): self._next() # skip the content after \\end
            elif tok.startswith('\\') and self._is_identifier_start(tok[1]):
                # handle command.
                cmd = CommandNode('', [], [])
                self.fill_command(cmd, tok)
                parent.children.append(cmd)
            elif tok == '{':
                # handle text block.
                block = TextBlockNode([])
                # self.match_brace(block, tok)
                self.parse_till(block, self._text_block_end)
                parent.children.append(block)
            elif tok == '$':
                # handle inline math mode.
                block = EnvironNode('math', [], [], [], is_numbered=True)
                self.parse_till(block, lambda t: t == '$')
                parent.children.append(block)
            elif tok == '\\[':
                block = EnvironNode('displaymath', [], [], [], is_numbered=True)
                self.parse_till(block, lambda t: t == '\\]')
                parent.children.append(block)
            else:
                # handle text token.
                parent.children.append(TextNode(tok))


def always_cont(tok:str) : return False

def _split_paragraphs(node: NodeBase):
    if isinstance(node, EnvironNode):
        node.split_by_paragraphs()

def parse_trivial(main_tex: str) -> NodeBase:
    """
    This simply groups tokens into CommandNode and EnvironNode,
    without trying to expand 'include/input' commands, nor
    split by paragraphs.
    """
    tokenizer = FileTokenizer(main_tex)
    parser = Parser(tokenizer)
    top = NodeBase([])
    parser.parse_till(top, always_cont)
    return top

def _expand_include_cmd(node: NodeBase):
    # replace '\include' and '\input' with the root node of included file.
    children = []
    for child in node.children:
        if not isinstance(child, CommandNode) or child.name not in ['include', 'input']:
            _expand_include_cmd(child)
            children.append(child)
        else:
            if child.args:
                arg0 = child.args[0]
                if arg0.children and isinstance(arg0.children[0], TextNode):
                    pth = arg0.children[0].word
                    if '.' not in os.path.basename(pth):
                        pth += '.tex'
                    if os.path.exists(pth):
                        new_node = parse_trivial(pth)
                        children += new_node.children
                    else:
                        raise FileNotFoundError(f'Included file {pth} not found.')
    node.children = children

class PrettyWriter():
    class Config():
        __slots__ = ['indent_size', 'linebreak', 'line_length']
        def __init__(self, indent_size: int = 2,
                     linebreak: str = '\n',
                     line_length: int = 80):
            self.indent_size = indent_size
            self.linebreak = linebreak
            self.line_length = line_length
    TAB_WIDTH = 4

    __slots__ = ['buf', 'config', 'col', 'nest_level', '_curline', 'autobreakoff']
    def __init__(self, buf: io.TextIOBase | io.TextIOWrapper, config: Config = None):
        self.buf = buf
        self.config = config if config else self.Config()
        self.col = 1
        self.nest_level = 0
        self._curline = ''
        self.autobreakoff = 0

    def autobreak(self) -> bool: return self.autobreakoff == 0

    def autobreak_off(self): self.autobreakoff += 1
    def autobreak_on(self):
        if self.autobreakoff > 0: self.autobreakoff -= 1

    def clear_current_line(self):
        self._curline = ''
        self.col = 1

    def clear_or_break(self):
        """
        If current line is filled with space, then clear it;
        else start a new line. This is useful when we want to
        avoid writing blanks at the beginning of a line.
        """
        if not self.autobreak(): return
        if self._curline.isspace() or self._curline == '':
            self.clear_current_line()
        else:
            self.newline()

    def finish(self):
        if self.autobreak():
            self._curline = self._curline.rstrip()
        if self._curline != '':
            self.buf.write(self._curline)
            self.buf.write(self.config.linebreak)

    def newline(self):
        # rm trailing spaces.
        if self.autobreak():
            self.buf.write(self._curline.rstrip())
        else:
            self.buf.write(self._curline)
        self._curline = ''
        self.buf.write(self.config.linebreak)
        self.col = 1

    def blank(self, blanks: str):
        if self.autobreak():
            if self.col > 1 and self._curline[-1].isspace():
                return # avoid writing adjacent blanks
            if self.col > self.config.line_length:
                self.newline()
            self._curline += ' ' # only write one blank
            self.col += 1
        else:
            # autobreak disabled. write `blanks` as is, and update column accordingly.
            self._curline += blanks
            for ch in blanks:
                if ch == '\t':
                    self.col += self.TAB_WIDTH
                elif ch == ' ':
                    self.col += 1
                else:
                    raise ValueError(f'Invalid blank character {bytes(ch, encoding="utf-8")}.')

    def word(self, token: str):
        """
        Using this method to write blank(s) or linebreak is incorrect,
        use `blank` (`newline`) instead, for better formatting.
        """
        l = len(token)
        if self.autobreak():
            if self.col + l > self.config.line_length:
                self.newline()
            self.pad_indent()
        self._curline += token
        self.col += l

    def pad_indent(self):
        npad = self.nest_level * self.config.indent_size - self.col + 1
        if npad > 0:
            self._curline += ' ' * npad
            self.col += npad

    def rem(self) -> int:
        """
        :returns: number of bytes that can still be written in the current line without breaking.
        """
        return self.config.line_length - self.col + 1

    def enter(self):
        self.nest_level += 1
    
    def leave(self):
        self.nest_level -= 1
        if self.nest_level < 0:
            raise ValueError('Negative nest level.')


def struct_sections(docnode: EnvironNode):
    """
    Structure those  command nodes representing article
    sections as a tree.
    """
    newroot = EnvironNode('document', [], [], [], is_numbered=True)
    top = SectionNode(SectionNode.SectionKind.TOP, '', False, [])
    stack = [top]

    for child in docnode.children:
        if isinstance(child, CommandNode) and child.is_section_cmd():
            name_node = child.args[0]
            if child.name == 'chapter':
                newsec = SectionNode(SectionNode.SectionKind.CHAPTER, name_node, child.is_numbered, [])
            elif child.name == 'section':
                newsec = SectionNode(SectionNode.SectionKind.SECTION, name_node, child.is_numbered, [])
            elif child.name == 'subsection':
                newsec = SectionNode(SectionNode.SectionKind.SUBSECTION, name_node, child.is_numbered, [])
            elif child.name == 'subsubsection':
                newsec = SectionNode(SectionNode.SectionKind.SUBSUBSECTION, name_node, child.is_numbered, [])
            else:
                # not a section command
                stack[-1].children.append(child)

            while stack and stack[-1].kind.value >= newsec.kind.value:
                stack.pop()
            stack[-1].children.append(newsec)
            stack.append(newsec)
        else:
            stack[-1].children.append(child)
    newroot.children = top.children
    return newroot


class Formatter():
    __slots__ = ['writer']
    NOBREAK_CMDS = set([
        # citation
        'cite', 'citep', 'citenum', 'citet', 'citeauthor', 'citeyear',
        # path/url
        'url', 'includegraphics', 'input', 'include',
        # label/ref
        'label', 'ref', 'pageref',
        # documentclass
        'documentclass',
        # text manipulation
        'textbf', 'textit', 'emph', 'texttt',
    ])

    @staticmethod
    def tabular_environ_formatter(formatter: 'Formatter', env: EnvironNode):
        formatter.word(f'\\begin{{{env.dump_name()}}}')
        formatter.writer.autobreak_off() # do not break in tabular environment, for better formatting.
        for arg in env.args:
            formatter.word('{')
            formatter.write(arg)
            formatter.word('}')
        for opt_arg in env.opt_args:
            formatter.word('[')
            formatter.write(opt_arg)
            formatter.word(']')
        formatter.writer.autobreak_on()
        formatter.newline()

        for child in env.children:
            if isinstance(child, CommandNode) and child.name == 'hline':
                formatter.writer.clear_or_break()
                formatter.write(child)
                formatter.newline()
            elif isinstance(child, TextNode) and child.word == '\\\\':
                formatter.write(child)
                formatter.newline()
            else:
                formatter.write(child)

        formatter.writer.clear_or_break()
        formatter.word(f'\\end{{{env.dump_name()}}}')

    @staticmethod
    def list_environ_formatter(formatter: 'Formatter', env: EnvironNode):
        formatter.word(f'\\begin{{{env.dump_name()}}}')
        for arg in env.args:
            formatter.word('{')
            formatter.write(arg)
            formatter.word('}')
        for opt_arg in env.opt_args:
            formatter.word('[')
            formatter.write(opt_arg)
            formatter.word(']')
        formatter.newline()

        for child in env.children:
            if isinstance(child, CommandNode) and child.name == 'item':
                formatter.writer.clear_or_break()
                formatter.write(child)
            elif isinstance(child, ParagraphNode):
                formatter.writer.clear_or_break()
                formatter.write(child)
            else:
                formatter.write(child)

        formatter.writer.clear_or_break()
        formatter.word(f'\\end{{{env.dump_name()}}}')

    def listing_environ_formatter(formatter: 'Formatter', env: EnvironNode):
        formatter.word(f'\\begin{{{env.dump_name()}}}')
        formatter.writer.autobreak_off() # do not break in listing environment, for better formatting.
        for arg in env.args:
            formatter.word('{')
            formatter.write(arg)
            formatter.word('}')
        for opt_arg in env.opt_args:
            formatter.word('[')
            formatter.write(opt_arg)
            formatter.word(']')

        # disable auto break when writing code snippets.
        for child in env.children:
            formatter.write(child)
        formatter.writer.autobreak_on()
        formatter.word(f'\\end{{{env.dump_name()}}}')

    # configure custom formatters for specific environments here.
    custom_environ_formatters = {
        'tabular': tabular_environ_formatter,
        'enumerate': list_environ_formatter,
        'itemize': list_environ_formatter,
        'lstlisting': listing_environ_formatter,
        'minted': listing_environ_formatter,
    }

    def __init__(self, buf: io.TextIOBase | io.TextIOWrapper,
                 indent_size: int = 2,
                 linebreak: str = '\n',
                 line_length: int = 80):
        config: PrettyWriter.Config = PrettyWriter.Config(indent_size, linebreak, line_length)
        self.writer = PrettyWriter(buf, config)

    def finish(self):
        self.writer.finish()

    def newline(self):
        self.writer.newline()

    def blank(self, blanks):
        self.writer.blank(blanks)

    def word(self, token: str):
        self.writer.word(token)

    def write(self, node: NodeBase): # generic
        if isinstance(node, TextNode):
            self._write_text(node)
        elif isinstance(node, TextBlockNode):
            self._write_text_block(node)
        elif isinstance(node, CommandNode):
            self._write_command(node)
        elif isinstance(node, SectionNode):
            self._write_section(node)
        elif isinstance(node, ParagraphNode):
            self._write_paragraph(node)
        elif isinstance(node, EnvironNode):
            self._write_environ(node)
        else:
            for child in node.children:
                self.write(child)

    def _write_comment(self, comment: str):
        if not self.writer.autobreak():
            # should not interpret current token as comment, 
            # since auto break is disabled. write it as is.
            self.word(comment)
            if comment.endswith('\n'):
                # as is often the case,
                # in the tokenizer stage, '\n' is
                # added to a comment token,
                # so we silenctly start a new line.
                self.writer.buf.write(self.writer._curline)
                self.writer.col = 1
                self.writer._curline = ''
            return
        elements = comment.split()
        for element in elements:
            l = len(element)
            if l >= self.writer.rem() - 1:
                self.newline()
                self.word('% ')
            self.word(element)
            self.blank(' ')
        self.newline()

    def _write_text(self, txt: TextNode):
        token = txt.word
        if token == '\n':
            self.newline()
        elif token.startswith('%'):
            self._write_comment(token)
        elif token.isspace():
            self.blank(token)
        else:
            self.word(txt.word)

    def _write_text_block(self, block: TextBlockNode):
        self.word('{')
        for child in block.children:
            self.write(child)
        self.word('}')

    def _write_command(self, cmd: CommandNode):
        disable_break = cmd.name in self.NOBREAK_CMDS
        first_token = f'\\{cmd.name}{"*" if not cmd.is_numbered else ""}'
        if disable_break:
            aux = io.StringIO()
            cmd.fmt(aux)
            self.word(aux.getvalue())
            return
        self.word(first_token)
        for opt_arg in cmd.opt_args:
            self.word('[')
            self.write(opt_arg)
            self.word(']')
        for arg in cmd.args:
            self.word('{')
            self.write(arg)
            self.word('}')

    def _write_section(self, sec: SectionNode):
        self.newline()
        self.writer.nest_level = 0
        if sec.kind == SectionNode.SectionKind.CHAPTER:
            self.word('\\chapter')
        elif sec.kind == SectionNode.SectionKind.SECTION:
            self.word('\\section')
        elif sec.kind == SectionNode.SectionKind.SUBSECTION:
            self.word('\\subsection')
        elif sec.kind == SectionNode.SectionKind.SUBSUBSECTION:
            self.word('\\subsubsection')
        else:
            raise ValueError('Invalid section kind.')

        if not sec.is_numbered:
            self.word('*')
        self.word('{')
        self.write(sec.name_node)
        self.word('}')

        for child in sec.children:
            self.newline()
            self.write(child)
        self.newline()

    def _write_environ(self, env: EnvironNode):
        if env.name in self.custom_environ_formatters and \
            self.writer.autobreak():
            self.custom_environ_formatters[env.name](self, env)
            return

        autobreakoff = env.name in EnvironNode.NO_AUTOBREAK_ENVIRONS
        if autobreakoff: self.writer.autobreak_off()

        # use default formatting implementation.
        self.word(f'\\begin{{{env.dump_name()}}}')
        for arg in env.args:
            self.word('{')
            self.write(arg)
            self.word('}')
        for opt_arg in env.opt_args:
            self.word('[')
            self.write(opt_arg)
            self.word(']')
        self.newline()

        nl_inc = int( 'document' != env.name )
        self.writer.nest_level += nl_inc
        for child in env.children:
            self.write(child)
        self.writer.nest_level -= nl_inc
        self.newline()
        self.word(f'\\end{{{env.dump_name()}}}')

        if autobreakoff: self.writer.autobreak_on()

    def _write_paragraph(self, par: ParagraphNode):
        # leave an empty line for readability
        children = par.children
        self.write(children[0])
        for i in range(1, len(children)):
            self.write(children[i])

def debug_dump(top: NodeBase, lv: int = 0):
    if isinstance(top, SectionNode):
        print('  ' * lv, end='')
        print(top.kind.value)
    elif isinstance(top, CommandNode):
        print('  ' * lv, end='')
        print(f'CMD: {top.name}, numbered={top.is_numbered}')
    elif isinstance(top, EnvironNode):
        print('  ' * lv, end='')
        print(f'ENV: {top.name}, numbered={top.is_numbered}')
    for child in top.children:
        debug_dump(child, lv + 1)


if __name__ == '__main__':
    top = parse_trivial(sys.argv[1])
    _expand_include_cmd(top)
    top.recurse(_split_paragraphs)

    for i, child in enumerate(top.children):
        if isinstance(child, EnvironNode) and child.name == 'document':
            top.children[i] = struct_sections(child)
            break

    # debug_dump(top)

    buf = io.StringIO()
    formatter = Formatter(buf)
    formatter.write(top)
    formatter.finish()
    print(buf.getvalue())


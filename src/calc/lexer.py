from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    NUMBER = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    EOF = auto()
    UNKNOWN = auto()
    IDENT = auto()
    SEMICOLON = auto()
    EQUALS = auto()
    DEF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str  # raw lexeme; "" for EOF


_SINGLE_CHAR: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    "=": TokenType.EQUALS,
}

_KEYWORDS: dict[str, TokenType] = {
    "def": TokenType.DEF,
}


class Lexer:
    def __init__(self, input: str) -> None:
        self._input = input
        self._cursor = 0

    def next_token(self) -> Token:
        self._skip_whitespace()
        if self._cursor >= len(self._input):
            return Token(TokenType.EOF, "")
        ch = self._peek()
        if ch in _SINGLE_CHAR:
            self._advance()
            return Token(_SINGLE_CHAR[ch], ch)
        if ch.isdigit() or ch == ".":
            return self._scan_number()
        if ch.isalpha() or ch == "_":
            return self._scan_ident()
        self._advance()
        return Token(TokenType.UNKNOWN, ch)

    def _peek(self) -> str:
        if self._cursor < len(self._input):
            return self._input[self._cursor]
        return ""

    def _advance(self) -> str:
        ch = self._peek()
        self._cursor += 1
        return ch

    def _skip_whitespace(self) -> None:
        while self._peek() in (" ", "\t"):
            self._advance()

    def _scan_number(self) -> Token:
        start = self._cursor
        if self._peek() == ".":
            self._advance()
            while self._peek().isdigit():
                self._advance()
        else:
            while self._peek().isdigit():
                self._advance()
            if self._peek() == ".":
                self._advance()
                while self._peek().isdigit():
                    self._advance()
        # optional exponent: e/E followed by optional +/- and digits
        if self._peek() in ("e", "E"):
            saved = self._cursor
            self._advance()                    # tentatively consume e/E
            if self._peek() in ("+", "-"):
                self._advance()
            if self._peek().isdigit():
                while self._peek().isdigit():
                    self._advance()            # valid exponent: consume all digits
            else:
                self._cursor = saved           # rollback — leave e/E for IDENT branch
        return Token(TokenType.NUMBER, self._input[start : self._cursor])

    def _scan_ident(self) -> Token:
        start = self._cursor
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self._input[start:self._cursor]
        return Token(_KEYWORDS.get(text, TokenType.IDENT), text)

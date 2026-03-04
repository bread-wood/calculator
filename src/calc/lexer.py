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
    EOF = auto()
    UNKNOWN = auto()


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
        if self._peek() in ("e", "E"):
            self._advance()
            if self._peek() in ("+", "-"):
                self._advance()
            while self._peek().isdigit():
                self._advance()
        return Token(TokenType.NUMBER, self._input[start : self._cursor])

from __future__ import annotations

from dataclasses import dataclass

from calc.errors import UnexpectedEnd, UnexpectedToken
from calc.lexer import Lexer, Token, TokenType


@dataclass
class Number:
    value: float


@dataclass
class BinaryOp:
    op: str
    left: ASTNode
    right: ASTNode


@dataclass
class UnaryOp:
    op: str
    operand: ASTNode


@dataclass
class Name:
    name: str


@dataclass
class Call:
    func: str
    args: list[ASTNode]


ASTNode = Number | BinaryOp | UnaryOp | Name | Call


class Parser:
    def __init__(self, lexer: Lexer) -> None:
        self._lexer = lexer
        self._current: Token = self._lexer.next_token()

    def parse(self) -> ASTNode:
        node = self._parse_expr()
        if self._current.type != TokenType.EOF:
            raise UnexpectedToken()
        return node

    def _advance(self) -> Token:
        previous = self._current
        self._current = self._lexer.next_token()
        return previous

    def _match(self, *types: TokenType) -> bool:
        if self._current.type in types:
            self._advance()
            return True
        return False

    def _expect(self, type: TokenType) -> Token:
        if self._current.type != type:
            if self._current.type == TokenType.EOF:
                raise UnexpectedEnd()
            raise UnexpectedToken()
        return self._advance()

    def _parse_expr(self) -> ASTNode:
        node = self._parse_term()
        while self._current.type in (TokenType.PLUS, TokenType.MINUS):
            op = self._advance().value
            right = self._parse_term()
            node = BinaryOp(op=op, left=node, right=right)
        return node

    def _parse_term(self) -> ASTNode:
        node = self._parse_factor()
        while self._current.type in (TokenType.STAR, TokenType.SLASH):
            op = self._advance().value
            right = self._parse_factor()
            node = BinaryOp(op=op, left=node, right=right)
        return node

    def _parse_factor(self) -> ASTNode:
        return self._parse_unary()

    def _parse_unary(self) -> ASTNode:
        if self._current.type == TokenType.MINUS:
            op = self._advance().value
            operand = self._parse_unary()
            return UnaryOp(op=op, operand=operand)
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        if self._current.type == TokenType.NUMBER:
            value = float(self._advance().value)
            return Number(value=value)
        if self._current.type == TokenType.LPAREN:
            self._advance()
            node = self._parse_expr()
            self._expect(TokenType.RPAREN)
            return node
        if self._current.type == TokenType.IDENT:
            name = self._advance().value
            if self._current.type == TokenType.LPAREN:
                self._advance()                # consume '('
                args = self._parse_arglist()
                self._expect(TokenType.RPAREN)
                return Call(func=name, args=args)
            return Name(name=name)
        if self._current.type == TokenType.EOF:
            raise UnexpectedEnd()
        raise UnexpectedToken()

    def _parse_arglist(self) -> list[ASTNode]:
        args: list[ASTNode] = []
        if self._current.type == TokenType.RPAREN:
            return args                    # zero-argument call: f()
        args.append(self._parse_expr())
        while self._current.type == TokenType.COMMA:
            self._advance()                # consume ','
            args.append(self._parse_expr())
        return args

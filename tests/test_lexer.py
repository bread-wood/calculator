import pytest
from calc.lexer import Lexer, Token, TokenType


def tokenize(src: str) -> list[Token]:
    lex = Lexer(src)
    tokens = []
    while True:
        t = lex.next_token()
        tokens.append(t)
        if t.type == TokenType.EOF:
            break
    return tokens


@pytest.mark.parametrize(
    "src, expected",
    [
        (
            "2 + 3",
            [
                Token(TokenType.NUMBER, "2"),
                Token(TokenType.PLUS, "+"),
                Token(TokenType.NUMBER, "3"),
                Token(TokenType.EOF, ""),
            ],
        ),
        (
            "10 / 4",
            [
                Token(TokenType.NUMBER, "10"),
                Token(TokenType.SLASH, "/"),
                Token(TokenType.NUMBER, "4"),
                Token(TokenType.EOF, ""),
            ],
        ),
        (
            "(2+3)*4",
            [
                Token(TokenType.LPAREN, "("),
                Token(TokenType.NUMBER, "2"),
                Token(TokenType.PLUS, "+"),
                Token(TokenType.NUMBER, "3"),
                Token(TokenType.RPAREN, ")"),
                Token(TokenType.STAR, "*"),
                Token(TokenType.NUMBER, "4"),
                Token(TokenType.EOF, ""),
            ],
        ),
        (
            "-3",
            [
                Token(TokenType.MINUS, "-"),
                Token(TokenType.NUMBER, "3"),
                Token(TokenType.EOF, ""),
            ],
        ),
    ],
)
def test_token_list(src, expected):
    assert tokenize(src) == expected


@pytest.mark.parametrize(
    "src, value",
    [
        ("42", "42"),
        ("3.14", "3.14"),
        (".5", ".5"),
        ("3.", "3."),
        ("100", "100"),
    ],
)
def test_number_literals(src, value):
    t = Lexer(src).next_token()
    assert t.type == TokenType.NUMBER
    assert t.value == value


@pytest.mark.parametrize(
    "ch, tt",
    [
        ("+", TokenType.PLUS),
        ("-", TokenType.MINUS),
        ("*", TokenType.STAR),
        ("/", TokenType.SLASH),
        ("(", TokenType.LPAREN),
        (")", TokenType.RPAREN),
    ],
)
def test_single_char_operators(ch, tt):
    t = Lexer(ch).next_token()
    assert t.type == tt
    assert t.value == ch


def test_unknown_character():
    lex = Lexer("@")
    t = lex.next_token()
    assert t.type == TokenType.UNKNOWN
    assert t.value == "@"


def test_unknown_then_eof():
    lex = Lexer("$")
    assert lex.next_token().type == TokenType.UNKNOWN
    assert lex.next_token().type == TokenType.EOF


def test_whitespace_skipped():
    lex = Lexer("  2  +  3  ")
    assert lex.next_token() == Token(TokenType.NUMBER, "2")
    assert lex.next_token() == Token(TokenType.PLUS, "+")
    assert lex.next_token() == Token(TokenType.NUMBER, "3")
    assert lex.next_token() == Token(TokenType.EOF, "")


def test_eof_idempotent():
    lex = Lexer("")
    assert lex.next_token().type == TokenType.EOF
    assert lex.next_token().type == TokenType.EOF



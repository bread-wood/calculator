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
        (",", TokenType.COMMA),
        (";", TokenType.SEMICOLON),
        ("=", TokenType.EQUALS),
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


@pytest.mark.parametrize("src, expected_value", [
    ("sqrt", "sqrt"), ("pi", "pi"), ("e", "e"),
    ("atan2", "atan2"), ("_var", "_var"), ("x1", "x1"),
])
def test_ident_token(src, expected_value):
    t = Lexer(src).next_token()
    assert t.type == TokenType.IDENT
    assert t.value == expected_value


def test_comma_token():
    t = Lexer(",").next_token()
    assert t == Token(TokenType.COMMA, ",")


def test_comma_in_sequence():
    tokens = tokenize("2,3")
    assert tokens == [
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.COMMA, ","),
        Token(TokenType.NUMBER, "3"),
        Token(TokenType.EOF, ""),
    ]


@pytest.mark.parametrize("src, expected_value", [
    ("1e10", "1e10"), ("1e+10", "1e+10"), ("1e-5", "1e-5"), ("1.5E2", "1.5E2"),
])
def test_sci_notation_unchanged(src, expected_value):
    t = Lexer(src).next_token()
    assert t.type == TokenType.NUMBER
    assert t.value == expected_value


def test_bare_e_after_number():
    tokens = tokenize("2e")
    assert tokens == [
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.IDENT, "e"),
        Token(TokenType.EOF, ""),
    ]


def test_2e_plus_produces_rollback():
    tokens = tokenize("2e+")
    assert tokens[0] == Token(TokenType.NUMBER, "2")
    assert tokens[1] == Token(TokenType.IDENT, "e")
    assert tokens[2] == Token(TokenType.PLUS, "+")


def test_2e_star_produces_rollback():
    tokens = tokenize("2e*3")
    assert tokens[0] == Token(TokenType.NUMBER, "2")
    assert tokens[1] == Token(TokenType.IDENT, "e")


def test_function_call_token_sequence():
    tokens = tokenize("sqrt(9)")
    assert tokens == [
        Token(TokenType.IDENT,  "sqrt"),
        Token(TokenType.LPAREN, "("),
        Token(TokenType.NUMBER, "9"),
        Token(TokenType.RPAREN, ")"),
        Token(TokenType.EOF,    ""),
    ]


def test_constant_in_expression():
    tokens = tokenize("2*pi")
    assert tokens == [
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.STAR,   "*"),
        Token(TokenType.IDENT,  "pi"),
        Token(TokenType.EOF,    ""),
    ]


def test_semicolon_token():
    t = Lexer(";").next_token()
    assert t == Token(TokenType.SEMICOLON, ";")


def test_equals_token():
    t = Lexer("=").next_token()
    assert t == Token(TokenType.EQUALS, "=")


def test_assignment_token_sequence():
    tokens = tokenize("x = 5")
    assert tokens == [
        Token(TokenType.IDENT,   "x"),
        Token(TokenType.EQUALS,  "="),
        Token(TokenType.NUMBER,  "5"),
        Token(TokenType.EOF,     ""),
    ]


def test_multi_statement_token_sequence():
    tokens = tokenize("x = 5; y = 2")
    assert tokens == [
        Token(TokenType.IDENT,      "x"),
        Token(TokenType.EQUALS,     "="),
        Token(TokenType.NUMBER,     "5"),
        Token(TokenType.SEMICOLON,  ";"),
        Token(TokenType.IDENT,      "y"),
        Token(TokenType.EQUALS,     "="),
        Token(TokenType.NUMBER,     "2"),
        Token(TokenType.EOF,        ""),
    ]


def test_trailing_semicolon():
    tokens = tokenize("x = 5;")
    assert tokens[-2] == Token(TokenType.SEMICOLON, ";")
    assert tokens[-1] == Token(TokenType.EOF, "")


def test_variable_reference_in_expression():
    tokens = tokenize("x * 2")
    assert tokens == [
        Token(TokenType.IDENT,  "x"),
        Token(TokenType.STAR,   "*"),
        Token(TokenType.NUMBER, "2"),
        Token(TokenType.EOF,    ""),
    ]

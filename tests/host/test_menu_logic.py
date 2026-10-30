"""Pruebas de menu_logic.c: navegación del Menu y entrada de iniciales (R7, R9.3)."""
from hypothesis import given, strategies as st

ROW_SONG, ROW_INSTR, ROW_DIFF, ROW_FAIL, ROW_PLAYERS, ROWS = 0, 1, 2, 3, 4, 5
ALL = 0b1111


def new_menu(ffi, lib):
    m = ffi.new("MenuSel *")
    lib.menu_sel_init(m)
    return m


def test_defaults_and_texts(ffi, lib):
    m = new_menu(ffi, lib)
    assert (m.row, m.song, m.instr, m.diff, m.no_fail, m.players) == (0, 0, 0, 1, False, 0)
    assert ffi.string(lib.menu_row_label(ROW_PLAYERS)) == b"JUGADORES"
    assert ffi.string(lib.menu_instr_name(3)) == b"BATERIA"
    assert ffi.string(lib.menu_diff_name(0)) == b"FACIL"
    assert ffi.string(lib.menu_players_name(2)) == b"2 JUGADORES COOP"


@given(st.lists(st.sampled_from([-1, 1]), max_size=40))
def test_rows_wrap(ffi, lib, moves):
    m = new_menu(ffi, lib)
    row = 0
    for d in moves:
        lib.menu_move(m, d)
        row = (row + d) % ROWS
        assert m.row == row


def test_down_wraps_to_top(ffi, lib):
    m = new_menu(ffi, lib)
    for _ in range(ROWS):
        lib.menu_move(m, 1)
    assert m.row == 0
    lib.menu_move(m, -1)
    assert m.row == ROWS - 1


def test_song_wraps_and_reports_change(ffi, lib):
    m = new_menu(ffi, lib)
    assert lib.menu_change(m, 1, 3, ALL) is True and m.song == 1
    lib.menu_change(m, 1, 3, ALL)
    lib.menu_change(m, 1, 3, ALL)
    assert m.song == 0
    lib.menu_change(m, -1, 3, ALL)
    assert m.song == 2


def test_difficulty_and_fail(ffi, lib):
    m = new_menu(ffi, lib)
    m.row = ROW_DIFF
    for expect in (2, 3, 0, 1):
        assert lib.menu_change(m, 1, 1, ALL) is False
        assert m.diff == expect
    m.row = ROW_FAIL
    lib.menu_change(m, 1, 1, ALL)
    assert m.no_fail
    lib.menu_change(m, -1, 1, ALL)
    assert not m.no_fail


def test_instrument_skips_missing(ffi, lib):
    m = new_menu(ffi, lib)
    m.row = ROW_INSTR
    avail = 0b0101   # guitarra y bajo
    lib.menu_change(m, 1, 1, avail)
    assert m.instr == 2
    lib.menu_change(m, 1, 1, avail)
    assert m.instr == 0


def test_fix_instruments_after_song_change(ffi, lib):
    m = new_menu(ffi, lib)
    m.instr = 3
    lib.menu_fix_instruments(m, 0b0011)
    assert m.instr in (0, 1)


def test_players_vs_copies_and_coop_distinct(ffi, lib):
    m = new_menu(ffi, lib)
    m.instr = 2
    m.row = ROW_PLAYERS
    lib.menu_change(m, 1, 1, ALL)       # VS
    assert m.players == 1 and m.instr2 == 2
    lib.menu_change(m, 1, 1, ALL)       # COOP: no pueden repetir instrumento
    assert m.players == 2 and m.instr2 != m.instr
    lib.menu_change(m, 1, 1, ALL)
    assert m.players == 0


# ---- Iniciales ----
def ini(ffi, lib, start=b"AAA"):
    e = ffi.new("IniEdit *")
    lib.ini_init(e, start)
    return e


def text(ffi, e):
    return bytes(ffi.buffer(e.ini, 3))


def test_initials_edit(ffi, lib):
    e = ini(ffi, lib)
    lib.ini_letter(e, 1)
    lib.ini_move(e, 1)
    for _ in range(14):
        lib.ini_letter(e, 1)
    lib.ini_move(e, 1)
    for _ in range(19):
        lib.ini_letter(e, 1)
    assert text(ffi, e) == b"BOT"
    lib.ini_confirm(e)
    assert e.done
    lib.ini_letter(e, 1)                # ya confirmadas: no cambian
    assert text(ffi, e) == b"BOT"


def test_initials_wrap(ffi, lib):
    e = ini(ffi, lib, b"AZ?")
    lib.ini_letter(e, -1)
    assert text(ffi, e)[0:1] == b"Z"
    lib.ini_move(e, -1)                 # de la primera a la tercera
    assert e.pos == 2
    lib.ini_move(e, 1)
    assert e.pos == 0
    assert text(ffi, e) == b"ZZA"       # '?' se normaliza a 'A'


@given(st.lists(st.tuples(st.booleans(), st.sampled_from([-1, 1])), max_size=60))
def test_initials_always_letters(ffi, lib, ops):
    e = ini(ffi, lib)
    for letter, d in ops:
        (lib.ini_letter if letter else lib.ini_move)(e, d)
        assert all(65 <= c <= 90 for c in text(ffi, e)) and e.pos < 3


def test_player2_menu_choices(ffi, lib):
    m = new_menu(ffi, lib)
    m.instr, m.instr2, m.diff, m.diff2 = 1, 0, 2, 1
    lib.menu_change2(m, 0, 1, ALL)             # 1 jugador: sin efecto
    assert m.instr2 == 0
    m.players = 2                              # COOP: no puede repetir el Instrument del 1
    lib.menu_change2(m, 0, 1, ALL)
    assert m.instr2 == 2
    lib.menu_change2(m, 0, -1, ALL)
    assert m.instr2 == 0
    lib.menu_change2(m, 1, 1, ALL)
    assert m.diff2 == 2 and lib.menu_diff_of_p2(m) == 2
    m.players = 1                              # VS: su Difficulty es la del 1
    lib.menu_change2(m, 1, 1, ALL)
    assert m.diff2 == 2 and lib.menu_diff_of_p2(m) == m.diff
    lib.menu_change2(m, 0, 1, ALL)
    assert m.instr2 == 1                       # en VS puede coincidir con el del 1

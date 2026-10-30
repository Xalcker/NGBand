/* Lógica pura del Menu y de las iniciales (ver menu_logic.h). */
#include "menu_logic.h"

static const char *const row_labels[MROW_COUNT] = {
  "CANCION", "INSTRUMENTO", "DIFICULTAD", "FALLO", "JUGADORES",
};
static const char *const instr_names[MENU_INSTRUMENTS] = { "GUITARRA", "TECLADO", "BAJO", "BATERIA" };
static const char *const diff_names[MENU_DIFFICULTIES] = { "FACIL", "MEDIO", "DIFICIL", "EXPERTO" };
static const char *const players_names[MPLAY_COUNT] = { "1 JUGADOR", "2 JUGADORES VS", "2 JUGADORES COOP" };

void menu_sel_init(MenuSel *m)
{
  m->row = MROW_SONG;
  m->song = 0;
  m->instr = 0;
  m->diff = 1;
  m->no_fail = false;
  m->players = MPLAY_SOLO;
  m->instr2 = 0;
  m->diff2 = 1;
}

static u8 wrap(u8 v, s8 delta, u8 n)
{
  return (u8)(((int)v + n + delta) % n);
}

void menu_move(MenuSel *m, s8 delta)
{
  m->row = wrap(m->row, delta < 0 ? -1 : 1, MROW_COUNT);
}

u8 menu_next_instr(u8 avail, u8 cur, s8 delta, u8 taken)
{
  u8 i, v = cur;
  for (i = 0; i < MENU_INSTRUMENTS; i++) {
    v = wrap(v, delta < 0 ? -1 : 1, MENU_INSTRUMENTS);
    if (((avail >> v) & 1) && v != taken) return v;
  }
  return cur;
}

void menu_fix_instruments(MenuSel *m, u8 avail)
{
  u8 taken = 0xFF;
  if (!((avail >> m->instr) & 1)) m->instr = menu_next_instr(avail, m->instr, 1, 0xFF);
  if (m->players == MPLAY_COOP) taken = m->instr;
  if (!((avail >> m->instr2) & 1) || m->instr2 == taken)
    m->instr2 = menu_next_instr(avail, m->instr2, 1, taken);
}

bool menu_change(MenuSel *m, s8 delta, u8 nsongs, u8 avail)
{
  delta = delta < 0 ? -1 : 1;
  switch (m->row) {
    case MROW_SONG:
      if (!nsongs) return false;
      m->song = wrap(m->song, delta, nsongs);
      return true;
    case MROW_INSTR:
      m->instr = menu_next_instr(avail, m->instr, delta, 0xFF);
      break;
    case MROW_DIFF:
      m->diff = wrap(m->diff, delta, MENU_DIFFICULTIES);
      break;
    case MROW_FAIL:
      m->no_fail = !m->no_fail;
      break;
    case MROW_PLAYERS:
      m->players = wrap(m->players, delta, MPLAY_COUNT);
      if (m->players == MPLAY_VS) m->instr2 = m->instr;   /* en VS el 2 copia al 1 */
      break;
    default: break;
  }
  menu_fix_instruments(m, avail);
  return false;
}

void menu_change2(MenuSel *m, u8 row2, s8 delta, u8 avail)
{
  delta = delta < 0 ? -1 : 1;
  if (m->players == MPLAY_SOLO) return;
  if (row2 == M2ROW_INSTR) {
    m->instr2 = menu_next_instr(avail, m->instr2, delta, m->players == MPLAY_COOP ? m->instr : 0xFF);
  } else if (m->players == MPLAY_COOP) {   /* en VS la dificultad del 2 es la del 1 */
    m->diff2 = wrap(m->diff2, delta, MENU_DIFFICULTIES);
  }
}

u8 menu_diff_of_p2(const MenuSel *m)
{
  return m->players == MPLAY_COOP ? m->diff2 : m->diff;
}

const char *menu_row_label(u8 row) { return row < MROW_COUNT ? row_labels[row] : ""; }
const char *menu_instr_name(u8 i) { return i < MENU_INSTRUMENTS ? instr_names[i] : ""; }
const char *menu_diff_name(u8 d) { return d < MENU_DIFFICULTIES ? diff_names[d] : ""; }
const char *menu_players_name(u8 p) { return p < MPLAY_COUNT ? players_names[p] : ""; }

void ini_init(IniEdit *e, const char *start)
{
  u8 i;
  for (i = 0; i < 3; i++) e->ini[i] = (start[i] >= 'A' && start[i] <= 'Z') ? start[i] : 'A';
  e->pos = 0;
  e->done = false;
}

void ini_letter(IniEdit *e, s8 delta)
{
  if (e->done) return;
  e->ini[e->pos] = (char)('A' + wrap((u8)(e->ini[e->pos] - 'A'), delta < 0 ? -1 : 1, 26));
}

void ini_move(IniEdit *e, s8 delta)
{
  if (e->done) return;
  e->pos = wrap(e->pos, delta < 0 ? -1 : 1, 3);
}

void ini_confirm(IniEdit *e) { e->done = true; }

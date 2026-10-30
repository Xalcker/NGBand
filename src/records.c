/* Récords en backup RAM del MVS (R9). Portado de GENBand/src/records.c.
 *
 * Backup RAM: 0xD00000, byte útil en las direcciones impares. Solo se escribe entre
 * REG_SRAMUNLOCK y REG_SRAMLOCK. Se escribe primero el cuerpo y al final la firma, así
 * una escritura interrumpida deja la firma o la suma inválidas (R9.3, R9.4).
 * Sin backup RAM (AES sin tarjeta) el juego sigue con la tabla en RAM. */

#include <string.h>
#include "records.h"

char last_initials[3] = { 'A', 'A', 'A' };

static RecordTable table;
static bool backup_ok = false;

u16 records_checksum(const u8 *buf, u16 len)
{
  u16 sum = 0;
  for (u16 i = 0; i < len; i++)
    sum = (u16)((u16)(sum << 1 | sum >> 15) + buf[i]);
  return sum;
}

void records_clear(RecordTable *t)
{
  memset(t, 0, sizeof *t);
  memcpy(t->magic, "NGBR", 4);
  t->version = RECORDS_VERSION;
}

static void put32(u8 *p, u32 v)
{
  p[0] = (u8)(v >> 24); p[1] = (u8)(v >> 16); p[2] = (u8)(v >> 8); p[3] = (u8)v;
}

static u32 get32(const u8 *p)
{
  return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

u16 records_encode(const RecordTable *t, u8 *out)
{
  memset(out, 0, RECORDS_ENCODED_SIZE);
  memcpy(out, "NGBR", 4);
  out[4] = RECORDS_VERSION;
  out[5] = t->count;
  for (u16 i = 0; i < MAX_RECORDS; i++) {
    u8 *p = out + RECORD_HEADER_BYTES + i * RECORD_ENTRY_BYTES;
    if (i >= t->count) continue;
    const RecordEntry *e = &t->e[i];
    put32(p, e->title_hash);
    p[4] = e->instrument;
    p[5] = e->difficulty;
    p[6] = e->stars;
    memcpy(p + 7, e->initials, 3);
    put32(p + 10, e->score);
  }
  const u16 body = RECORDS_ENCODED_SIZE - 2;
  const u16 sum = records_checksum(out, body);
  out[body] = (u8)(sum >> 8);
  out[body + 1] = (u8)sum;
  return RECORDS_ENCODED_SIZE;
}

bool records_decode(const u8 *buf, u16 len, RecordTable *t)
{
  const u16 body = RECORDS_ENCODED_SIZE - 2;
  records_clear(t);
  if (len < RECORDS_ENCODED_SIZE) return false;
  if (memcmp(buf, "NGBR", 4) != 0) return false;
  if (buf[4] != RECORDS_VERSION || buf[5] > MAX_RECORDS) return false;
  if (records_checksum(buf, body) != (u16)((u16)buf[body] << 8 | buf[body + 1])) return false;
  t->count = buf[5];
  for (u16 i = 0; i < t->count; i++) {
    const u8 *p = buf + RECORD_HEADER_BYTES + i * RECORD_ENTRY_BYTES;
    RecordEntry *e = &t->e[i];
    e->title_hash = get32(p);
    e->instrument = p[4];
    e->difficulty = p[5];
    e->stars = p[6];
    memcpy(e->initials, p + 7, 3);
    e->score = get32(p + 10);
  }
  t->checksum = (u16)((u16)buf[body] << 8 | buf[body + 1]);
  return true;
}

#ifndef NGBAND_HOST
/* ---- Acceso a hardware (solo en la ROM) ---- */
#define BRAM_BASE      ((volatile u8 *)0xD00000)
#define REG_SRAMLOCK   (*(volatile u8 *)0x3A000D)
#define REG_SRAMUNLOCK (*(volatile u8 *)0x3A001D)

static void bram_unlock(void) { REG_SRAMUNLOCK = 0; }
static void bram_lock(void)   { REG_SRAMLOCK = 0; }
static u8   bram_read(u16 i)  { return BRAM_BASE[i * 2 + 1]; }
static void bram_write(u16 i, u8 v) { BRAM_BASE[i * 2 + 1] = v; }

static bool bram_load(u8 *buf)
{
  for (u16 i = 0; i < RECORDS_ENCODED_SIZE; i++) buf[i] = bram_read(i);
  return true;
}

/* Cuerpo primero y firma al final. Devuelve false si la firma no se lee de vuelta (sin backup RAM). */
static bool bram_store(const u8 *buf)
{
  bram_unlock();
  for (u16 i = 4; i < RECORDS_ENCODED_SIZE; i++) bram_write(i, buf[i]);
  for (u16 i = 0; i < 4; i++) bram_write(i, buf[i]);
  bool ok = true;
  for (u16 i = 0; i < 4; i++) if (bram_read(i) != buf[i]) ok = false;
  bram_lock();
  return ok;
}
#else
static bool bram_load(u8 *buf) { (void)buf; return false; }
static bool bram_store(const u8 *buf) { (void)buf; return false; }
#endif

void records_init(void)
{
  u8 buf[RECORDS_ENCODED_SIZE];
  backup_ok = bram_load(buf);
  if (!backup_ok || !records_decode(buf, RECORDS_ENCODED_SIZE, &table))
    records_clear(&table);
}

const RecordTable *records_table(void) { return &table; }
bool records_backup_ok(void) { return backup_ok; }

static RecordEntry *find(u32 hash, u8 instrument, u8 difficulty)
{
  for (u16 i = 0; i < table.count; i++) {
    RecordEntry *e = &table.e[i];
    if (e->title_hash == hash && e->instrument == instrument && e->difficulty == difficulty)
      return e;
  }
  return NULL;
}

bool record_get(u32 title_hash, u8 instrument, u8 difficulty, RecordEntry *out)
{
  const RecordEntry *e = find(title_hash, instrument, difficulty);
  if (!e) return false;
  if (out) *out = *e;
  return true;
}

bool record_beats(u32 title_hash, u8 instrument, u8 difficulty, u32 score)
{
  const RecordEntry *e = find(title_hash, instrument, difficulty);
  return score > 0 && (!e || score > e->score);
}

void record_save(u32 title_hash, u8 instrument, u8 difficulty, u32 score,
                 const char *initials, u8 stars)
{
  RecordEntry *e = find(title_hash, instrument, difficulty);
  if (!e && table.count < MAX_RECORDS)
    e = &table.e[table.count++];
  if (!e) {  /* tabla llena: se reemplaza el registro de menor puntaje */
    e = &table.e[0];
    for (u16 i = 1; i < table.count; i++)
      if (table.e[i].score < e->score) e = &table.e[i];
  }
  e->title_hash = title_hash;
  e->instrument = instrument;
  e->difficulty = difficulty;
  e->score = score;
  memcpy(e->initials, initials, 3);
  e->stars = stars;
  memcpy(last_initials, initials, 3);

  u8 buf[RECORDS_ENCODED_SIZE];
  records_encode(&table, buf);
  table.checksum = (u16)((u16)buf[RECORDS_ENCODED_SIZE - 2] << 8 | buf[RECORDS_ENCODED_SIZE - 1]);
  backup_ok = bram_store(buf);
}

bool is_record_eligible(const RecordRun *run)
{
  if (run->mode == RECORD_MODE_VS) return false;
  if (run->lost || run->no_fail || run->mirror || run->practice) return false;
  if (!run->speed_default || !run->fall_default) return false;
  if (run->mode == RECORD_MODE_COOP && run->p2_lost) return false;
  return true;
}

bool record_submit(const RecordRun *run, u32 title_hash, u8 instrument, u8 difficulty,
                   u32 score, const char *initials, u8 stars)
{
  if (!is_record_eligible(run) || !record_beats(title_hash, instrument, difficulty, score))
    return false;
  record_save(title_hash, instrument, difficulty, score, initials, stars);
  return true;
}

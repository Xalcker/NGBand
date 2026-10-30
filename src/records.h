/* Records_Store: tabla de récords y su serialización (R9). Sin dependencia de hardware
 * salvo el volcado a backup RAM, que records.c deja fuera del build del host. */
#ifndef NGBAND_RECORDS_H
#define NGBAND_RECORDS_H

#include "types.h"

enum {
  MAX_RECORDS = 128,
  RECORD_ENTRY_BYTES = 14,    /* hash 4 + instr 1 + dif 1 + estrellas 1 + iniciales 3 + puntaje 4 */
  RECORD_HEADER_BYTES = 6,    /* firma 4 + versión 1 + cuenta 1 */
  RECORDS_ENCODED_SIZE = 6 + 128 * 14 + 2,
  RECORDS_VERSION = 1
};

typedef struct {
  u32  title_hash;
  u8   instrument, difficulty;
  u8   stars;
  char initials[3];
  u32  score;
} RecordEntry;

typedef struct {
  char  magic[4];           /* "NGBR" */
  u8    version;
  u8    count;
  RecordEntry e[MAX_RECORDS];
  u16   checksum;           /* suma de comprobación de todo lo anterior */
} RecordTable;

/* Suma de comprobación (rotación + suma) de `len` bytes. */
u16  records_checksum(const u8 *buf, u16 len);

/* Serializa en big endian a `out` (RECORDS_ENCODED_SIZE bytes). Devuelve los bytes escritos. */
u16  records_encode(const RecordTable *t, u8 *out);

/* Lee `len` bytes. Devuelve true si firma, versión, cuenta y suma son válidas;
 * si no, deja `t` vacía (R9.4) y devuelve false. */
bool records_decode(const u8 *buf, u16 len, RecordTable *t);

/* Tabla vacía con firma y versión. */
void records_clear(RecordTable *t);

/* Tabla en RAM (fuente de verdad en ejecución). */
const RecordTable *records_table(void);
bool records_backup_ok(void);  /* false si no hay backup RAM utilizable */

/* Carga desde backup RAM; tabla vacía si no hay o está dañada. */
void records_init(void);

bool record_get(u32 title_hash, u8 instrument, u8 difficulty, RecordEntry *out);
bool record_beats(u32 title_hash, u8 instrument, u8 difficulty, u32 score);

/* Guarda un récord en la tabla en RAM y la vuelca a backup RAM si existe. */
void record_save(u32 title_hash, u8 instrument, u8 difficulty, u32 score,
                 const char *initials, u8 stars);

/* Elegibilidad (R9.5, R10.3, R10.8). Entradas planas, sin depender de GameConfig.
 * `mode` sigue el orden del diseño: SOLO=0, VS=1, COOP=2. */
enum { RECORD_MODE_SOLO = 0, RECORD_MODE_VS = 1, RECORD_MODE_COOP = 2 };

typedef struct {
  u8   mode;                 /* RECORD_MODE_* */
  bool lost;                 /* la partida se perdió (vida en 0, P1 en SOLO) */
  bool p2_lost;              /* COOP: el segundo jugador cayó */
  bool no_fail;              /* SIN FALLO */
  bool mirror;               /* ESPEJO */
  bool speed_default;        /* velocidad en su valor normal */
  bool fall_default;         /* caída en su valor normal */
  bool practice;             /* Practice_Mode */
  /* EFECTO AL FALLAR (fail_fx) no afecta: no se pasa. */
} RecordRun;

/* Falso si perdió, SIN FALLO, opciones distintas de la normal, práctica o VS;
 * en COOP solo si los dos terminan en pie. */
bool is_record_eligible(const RecordRun *run);

/* Si la partida es elegible y supera el récord actual, lo guarda y devuelve true. */
bool record_submit(const RecordRun *run, u32 title_hash, u8 instrument, u8 difficulty,
                   u32 score, const char *initials, u8 stars);

extern char last_initials[3];

#endif /* NGBAND_RECORDS_H */

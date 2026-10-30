#include "spr_diff.h"
#include <string.h>

static inline bool vq_push_inline(VQueue *q, u8 prio, u16 addr, u16 val)
{
  VqEntry *e;
  if (prio == VQ_PRIO_HI) {
    if (q->nhi >= VQ_HI_CAP) return false;
    e = &q->hi[q->nhi++];
  } else {
    if (q->nlo >= VQ_LO_CAP) return false;
    e = &q->lo[q->nlo++];
  }
  e->addr = addr;
  e->val = val;
  return true;
}

/* ---- Cola ---- */
void vq_init(VQueue *q) { memset(q, 0, sizeof *q); }

bool vq_push(VQueue *q, u8 prio, u16 addr, u16 val)
{
  return vq_push_inline(q, prio, addr, val);
}

bool vq_pop(VQueue *q, VqEntry *out)
{
  if (q->head_hi < q->nhi) { *out = q->hi[q->head_hi++]; goto done; }
  if (q->head_lo < q->nlo) { *out = q->lo[q->head_lo++]; goto done; }
  return false;
done:
  /* al vaciarse una cola, se reinicia para reutilizar el espacio */
  if (q->head_hi == q->nhi) { q->head_hi = q->nhi = 0; }
  if (q->head_lo == q->nlo) { q->head_lo = q->nlo = 0; }
  return true;
}

u16 vq_pending(const VQueue *q)
{
  return (u16)((q->nhi - q->head_hi) + (q->nlo - q->head_lo));
}

/* ---- Diff ---- */
typedef u32 __attribute__((may_alias, aligned(2))) u32a;

/* El 68000 lee 32 bits de una dirección par: se comparan dos palabras a la vez y solo se mira cada una
 * cuando el par cambió (lo normal es que casi nada cambie entre cuadros). */
u16 vdiff_words(const u16 *want, u16 *sent, u16 n, u16 vram_base, VQueue *q, u8 prio)
{
  u16 count = 0, i = 0;
  {
    for (; i + 1 < n; i += 2) {
      u16 k;
      if (*(const u32a *)(want + i) == *(const u32a *)(sent + i)) continue;
      for (k = i; k < i + 2; k++) {
        if (want[k] == sent[k]) continue;
        if (!vq_push(q, prio, (u16)(vram_base + k), want[k])) return count | 0x8000u;
        sent[k] = want[k];
        count++;
      }
    }
  }
  for (; i < n; i++) {
    if (want[i] == sent[i]) continue;
    if (!vq_push(q, prio, (u16)(vram_base + i), want[i])) return count | 0x8000u;
    sent[i] = want[i];
    count++;
  }
  return count;
}

/* ---- Sprites ---- */
void spr_shadow_init(SpriteShadow *s) { memset(s, 0, sizeof *s); }

static const u16 class_base[SPR_CLASS_COUNT] = {
  0, SPR_POOL_GEM, SPR_POOL_GEM + SPR_POOL_TAIL,
  SPR_POOL_GEM + SPR_POOL_TAIL + SPR_POOL_LINE
};
static const u16 class_size[SPR_CLASS_COUNT] = {
  SPR_POOL_GEM, SPR_POOL_TAIL, SPR_POOL_LINE, SPR_POOL_STAGE
};

u16 spr_class_base(u8 cls) { return class_base[cls]; }
u16 spr_class_size(u8 cls) { return class_size[cls]; }

void spr_pool_begin(SpriteShadow *s)
{
  for (u8 c = 0; c < SPR_CLASS_COUNT; c++) s->pool_cur[c] = 0;
}

int spr_pool_alloc(SpriteShadow *s, u8 cls)
{
  if (cls >= SPR_CLASS_COUNT || s->pool_cur[cls] >= class_size[cls]) return -1;
  return class_base[cls] + s->pool_cur[cls]++;
}

static void mark(SpriteShadow *s, u16 idx)
{
  if (!s->dirty[idx]) {
    s->dirty[idx] = 1;
    s->dirty_list[s->ndirty++] = idx;
  }
}

void spr_pool_end(SpriteShadow *s)
{
  for (u8 c = 0; c < SPR_CLASS_COUNT; c++) {
    for (u16 i = s->pool_cur[c]; i < s->pool_prev[c]; i++)
      spr_hide(s, (u16)(class_base[c] + i));
    s->pool_prev[c] = s->pool_cur[c];
  }
}

void spr_hide(SpriteShadow *s, u16 idx)
{
  if (idx < SPR_COUNT && s->want.scb3[idx]) {
    s->want.scb3[idx] = 0;
    mark(s, idx);
  }
}

void spr_set(SpriteShadow *s, u16 idx, s16 x, s16 y, u32 tile, u8 pal,
             u8 hshrink, u8 vshrink, u8 height, u8 flip)
{
  if (idx >= SPR_COUNT) return;
  if (height == 0) { spr_hide(s, idx); return; }
  if (height > SPR_ROWS_MAX) height = SPR_ROWS_MAX;
  u16 *c = &s->want.scb1[idx * SPR_SCB1_WORDS];
  bool changed = false;
  for (u8 r = 0; r < SPR_ROWS_MAX; r++) {
    u32 t = tile + r;
    u16 lo = (u16)t, at = (u16)(((u16)pal << 8) | (((t >> 16) & 0xF) << 4) | (flip & 3));
    if (c[r * 2] != lo || c[r * 2 + 1] != at) { c[r * 2] = lo; c[r * 2 + 1] = at; changed = true; }
  }
  u16 w2 = (u16)(((hshrink & 0xF) << 8) | vshrink);
  u16 w3 = (u16)((((496 - y) & 0x1FF) << 7) | (height & 0x3F));
  u16 w4 = (u16)((x & 0x1FF) << 7);
  if (s->want.scb2[idx] != w2 || s->want.scb3[idx] != w3 || s->want.scb4[idx] != w4) {
    s->want.scb2[idx] = w2; s->want.scb3[idx] = w3; s->want.scb4[idx] = w4; changed = true;
  }
  if (changed) mark(s, idx);
}

/* Encola los cambios de un sprite; false si la cola se llenó (lo pendiente queda para el próximo cuadro). */
#define PUSH_IF(W, S, A) do { if ((W) != (S)) { if (!vq_push_inline(q, prio, (A), (W))) return false; (S) = (W); } } while (0)
static bool flush_one(SpriteShadow *s, VQueue *q, u16 i)
{
  u8 prio = i >= class_base[SPR_CLASS_STAGE] ? VQ_PRIO_LO : VQ_PRIO_HI;
  const u16 *w = &s->want.scb1[i * SPR_SCB1_WORDS];
  u16 *t = &s->sent.scb1[i * SPR_SCB1_WORDS];
  const u16 n = (u16)(i + SPR_HW_BASE);
  u16 a = (u16)(VRAM_SCB1 + n * 64), k;
  for (k = 0; k < SPR_SCB1_WORDS; k++) PUSH_IF(w[k], t[k], (u16)(a + k));
  PUSH_IF(s->want.scb2[i], s->sent.scb2[i], (u16)(VRAM_SCB2 + n));
  PUSH_IF(s->want.scb3[i], s->sent.scb3[i], (u16)(VRAM_SCB3 + n));
  PUSH_IF(s->want.scb4[i], s->sent.scb4[i], (u16)(VRAM_SCB4 + n));
  return true;
}
#undef PUSH_IF

u16 spr_flush(SpriteShadow *s, VQueue *q)
{
  u16 before = vq_pending(q), k = 0, keep = 0;
  /* Solo los sprites marcados. Si la cola se llena, los que faltan siguen marcados para el próximo cuadro. */
  for (; k < s->ndirty; k++) {
    u16 i = s->dirty_list[k];
    if (flush_one(s, q, i)) s->dirty[i] = 0;
    else s->dirty_list[keep++] = i;
  }
  s->ndirty = keep;
  return (u16)(vq_pending(q) - before);
}

/* ---- Fix_Layer ---- */
void fix_shadow_init(FixShadow *f) { memset(f, 0, sizeof *f); }

void fix_put(FixShadow *f, u8 col, u8 row, u16 tile, u8 pal)
{
  if (col >= FIX_COLS || row >= FIX_ROWS) return;
  u16 v = (u16)(((u16)(pal & 0xF) << 12) | (tile & 0x0FFF));
  u16 *w = &f->want[col * FIX_ROWS + row];
  if (*w != v) { *w = v; f->dirty[col] = 1; }
}

void fix_clear(FixShadow *f)
{
  memset(f->want, 0, sizeof f->want);
  memset(f->dirty, 1, sizeof f->dirty);
}

u16 fix_flush_to(FixShadow *f, VQueue *q)
{
  u16 n = 0;
  for (u8 c = 0; c < FIX_COLS; c++) {
    u16 r;
    if (!f->dirty[c]) continue;
    r = vdiff_words(&f->want[c * FIX_ROWS], &f->sent[c * FIX_ROWS], FIX_ROWS, (u16)(VRAM_FIX + c * FIX_ROWS), q,
                    VQ_PRIO_HI);
    n += r & 0x7FFFu;
    if (r & 0x8000u) break;            /* cola llena: la columna sigue marcada */
    f->dirty[c] = 0;
  }
  return n;
}

#include "vram_queue.h"
#include "neogeo.h"

VQueue g_vq;
volatile u8 g_vq_lock;

void vq_hw_init(void) { vq_init(&g_vq); }

/* Vacía una de las dos colas (alta o baja prioridad) hasta `budget` palabras. Recorre el arreglo con punteros:
 * vq_pop por palabra (llamada, copia y comprobaciones) era una parte grande del ISR en los cuadros con muchos
 * cambios. `*next` es la dirección que la VRAM ya tiene por autoincremento. */
static u16 drain(const VqEntry *e, u16 *head, u16 *count, u16 budget, u16 *next)
{
  const VqEntry *const end = e + *count;
  const u16 h0 = *head;
  u16 n;
  u16 addr = *next;
  e += h0;
  if ((u16)(end - e) < budget) budget = (u16)(end - e);
  for (n = budget; n; n--, e++) {
    if (e->addr != addr) REG_VRAMADDR = e->addr;
    REG_VRAMRW = e->val;
    addr = (u16)(e->addr + 1);
  }
  *next = addr;
  *head = (u16)(h0 + budget);
  if (*head == *count) *head = *count = 0;   /* vacía: se reutiliza el espacio desde el principio */
  return budget;
}

u16 vq_flush(u16 budget)
{
  u16 n, next = 0xFFFF;            /* 0xFFFF no es una dirección que se encole: fuerza la primera */
  if (g_vq_lock) return 0;         /* el bucle principal está a mitad de encolar */
  REG_VRAMMOD = 1;
  n = drain(g_vq.hi, &g_vq.head_hi, &g_vq.nhi, budget, &next);
  if (n < budget && g_vq.head_hi == 0 && g_vq.nhi == 0)
    n = (u16)(n + drain(g_vq.lo, &g_vq.head_lo, &g_vq.nlo, (u16)(budget - n), &next));
  return n;
}

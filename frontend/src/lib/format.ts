// Formatting helpers (Intl, IST timezone, Indian Rupee)

export function formatMoney(val: string | number | null | undefined): string {
  if (val === null || val === undefined || val === '') return '₹0.00'
  const num = typeof val === 'number' ? val : parseFloat(val)
  if (isNaN(num)) return '₹0.00'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(num)
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return new Intl.DateTimeFormat('en-IN', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'Asia/Kolkata',
    }).format(d)
  } catch {
    return iso
  }
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return new Intl.DateTimeFormat('en-IN', {
      dateStyle: 'medium',
      timeZone: 'Asia/Kolkata',
    }).format(d)
  } catch {
    return iso
  }
}

export function formatDurationHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '—'
  if (hours === 1) return '1 hour'
  return `${hours} hours`
}

/**
 * Format a Date to the value expected by <input type="datetime-local"> (YYYY-MM-DDTHH:mm)
 */
export function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  const year = date.getFullYear()
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())
  return `${year}-${month}-${day}T${hours}:${minutes}`
}


const dateTimeFormat = new Intl.DateTimeFormat('es-CL', { dateStyle: 'short', timeStyle: 'medium' })

export function formatDateTime(value: string): string {
  return dateTimeFormat.format(new Date(value))
}

export function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? `No se pudo completar la operación (${error.message}).`
    : 'No se pudo conectar con el servidor.'
}

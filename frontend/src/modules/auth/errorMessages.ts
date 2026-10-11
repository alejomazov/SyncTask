import { ApiError } from '../../services/apiClient'

const MESSAGES: Record<number, string> = {
  401: 'Correo o contraseña incorrectos.',
  403: 'Tu cuenta está deshabilitada. Contacta al administrador.',
  409: 'Ya existe una cuenta con ese correo.',
  422: 'Revisa los datos ingresados.',
}

export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.status] ?? 'Ocurrió un error. Inténtalo nuevamente.'
  }
  return 'No se pudo conectar con el servidor.'
}

import { useState, type FormEvent } from 'react'

import { settingsService } from '../../services/settingsService'
import type { Settings } from '../../types/settings'

type Message = { text: string; ok: boolean }

interface Props {
  settings: Settings
  onChange: (settings: Settings) => void
}

const PLACEHOLDER =
  'Ejemplo: Resume mi agenda agrupada por día, con la hora primero. Lista las tareas ' +
  'ordenadas por fecha de vencimiento y avísame de las atrasadas. Trátame de tú.'

export default function InstructionsCard({ settings, onChange }: Props) {
  const saved = settings.custom_instructions ?? ''
  const [text, setText] = useState(saved)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<Message | null>(null)

  async function store(value: string, success: string) {
    setBusy(true)
    setMessage(null)
    try {
      const updated = await settingsService.setCustomInstructions(value)
      onChange(updated)
      setText(updated.custom_instructions ?? '')
      setMessage({ text: success, ok: true })
    } catch {
      setMessage({ text: 'No se pudieron guardar las instrucciones.', ok: false })
    } finally {
      setBusy(false)
    }
  }

  function save(event: FormEvent) {
    event.preventDefault()
    void store(
      text,
      text.trim()
        ? 'Instrucciones guardadas. Se aplican desde tu próximo mensaje.'
        : 'Instrucciones eliminadas.',
    )
  }

  function remove() {
    if (!window.confirm('¿Seguro que quieres borrar tus instrucciones?')) return
    void store('', 'Instrucciones eliminadas.')
  }

  return (
    <section className="panel settings-section">
      <h2>Instrucciones para el asistente</h2>
      <p className="muted">
        Escribe cómo te gustaría que el asistente te responda y resuma tus tareas y calendarios:
        tono, extensión, orden o idioma. Se aplican a todos los modelos. No cambian el modo de
        ejecución ni las confirmaciones.
      </p>
      <form className="instructions-form" onSubmit={save}>
        <textarea
          aria-label="Instrucciones para el asistente"
          rows={6}
          maxLength={settings.custom_instructions_max_length}
          placeholder={PLACEHOLDER}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="instructions-actions">
          <span className="muted">
            {text.length} / {settings.custom_instructions_max_length}
          </span>
          <button type="submit" disabled={busy || text.trim() === saved}>
            {busy ? 'Guardando…' : 'Guardar'}
          </button>
          {saved && (
            <button type="button" className="button-secondary" disabled={busy} onClick={remove}>
              Borrar
            </button>
          )}
        </div>
      </form>
      {message && (
        <p
          className={message.ok ? 'form-success' : 'form-error'}
          role={message.ok ? 'status' : 'alert'}
        >
          {message.text}
        </p>
      )}
    </section>
  )
}

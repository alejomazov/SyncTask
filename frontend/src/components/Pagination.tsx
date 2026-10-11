interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
}

export default function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="pagination">
      <button
        type="button"
        className="button-secondary"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        Anterior
      </button>
      <span>
        Página {page} de {pageCount} · {total} {total === 1 ? 'registro' : 'registros'}
      </span>
      <button
        type="button"
        className="button-secondary"
        disabled={page >= pageCount}
        onClick={() => onChange(page + 1)}
      >
        Siguiente
      </button>
    </div>
  )
}

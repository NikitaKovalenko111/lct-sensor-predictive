import { SearchX } from 'lucide-react'

export function EmptyState({ title = 'Ничего не найдено', description = 'Измените параметры фильтрации.' }: { title?: string; description?: string }) {
  return <div className="empty-state"><SearchX size={28} /><strong>{title}</strong><span>{description}</span></div>
}

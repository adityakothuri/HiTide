import { CircleCheck } from 'lucide-react'
import type { EvidenceState, Task } from '../types'
import { accessChip, ageLabel, isHighPriority, latestDirect, type QueueTab, taskSummary, tasksFor } from './derive'
import s from './ops.module.css'

interface Props {
  state: EvidenceState
  tab: QueueTab
  onTab: (tab: QueueTab) => void
  selectedId: string
  onSelect: (roadId: string) => void
  now: number
  onLoadDemo: () => void
  busy: boolean
}

const TABS: { id: QueueTab; label: string }[] = [
  { id: 'review', label: 'Needs review' },
  { id: 'assigned', label: 'Assigned' },
]

export function Queue({ state, tab, onTab, selectedId, onSelect, now, onLoadDemo, busy }: Props) {
  const tasks = tasksFor(state, tab)
  const completed = state.tasks.filter((t) => t.status === 'completed')
  return (
    <section className={s.queue} aria-labelledby="queue-heading">
      <h2 id="queue-heading" className={s.srOnly}>Inspection queue</h2>
      <div className={s.segmented} role="tablist" aria-label="Queue">
        {TABS.map((t) => {
          const count = tasksFor(state, t.id).length
          return (
            <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} className={s.segment} onClick={() => onTab(t.id)}>
              {t.label}<span className={s.segmentCount}>{count}</span>
            </button>
          )
        })}
      </div>
      <ul className={s.queueList} role="tabpanel">
        {tasks.map((task) => (
          <QueueItem key={task.id} state={state} task={task} isSelected={task.road_id === selectedId} onSelect={onSelect} now={now} />
        ))}
      </ul>
      {tasks.length === 0 && (
        <div className={s.empty}>
          <CircleCheck size={22} aria-hidden />
          <p>{tab === 'assigned' ? 'No inspections assigned.' : 'No crossings waiting for review.'}</p>
          {tab === 'review' && state.communities.length === 0 && (
            <>
              <p className={s.muted}>Access impact needs community origins and destinations. Load the labeled exercise to try the workflow.</p>
              <button type="button" className={s.linkButton} onClick={onLoadDemo} disabled={busy}>Load two-exit exercise</button>
            </>
          )}
        </div>
      )}
      {completed.length > 0 && (
        <details className={s.completed}>
          <summary>Completed <span className={s.num}>{completed.length}</span></summary>
          <ul className={s.queueList}>
            {completed.map((task) => (
              <QueueItem key={task.id} state={state} task={task} isSelected={task.road_id === selectedId} onSelect={onSelect} now={now} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

interface ItemProps {
  state: EvidenceState
  task: Task
  isSelected: boolean
  onSelect: (roadId: string) => void
  now: number
}

function QueueItem({ state, task, isSelected, onSelect, now }: ItemProps) {
  const road = state.roads.find((r) => r.id === task.road_id)
  const chip = road ? accessChip(road) : null
  const latest = road ? latestDirect(state, road) : undefined
  const age = ageLabel(latest?.observed_at, now)
  const urgent = isHighPriority(task) && task.status !== 'completed'
  const reason = taskSummary(state, task)
  return (
    <li>
      <button type="button" className={`${s.queueItem} ${isSelected ? s.queueItemOn : ''}`} aria-current={isSelected} onClick={() => onSelect(task.road_id)}
        title={age ? `Latest road evidence ${age === 'just now' ? 'just now' : `${age} old`}` : 'No direct road evidence'}>
        <span className={s.queueText}>
          <span className={s.queueName}>
            {urgent && <span className={s.priorityDot} aria-hidden />}
            {urgent && <span className={s.srOnly}>High priority: </span>}
            {task.road_name}
          </span>
          <span className={s.queueReason}>{reason}</span>
        </span>
        {chip && <span className={`${s.chip} ${s[`chip_${chip.tone}`]}`}>{chip.label}</span>}
      </button>
    </li>
  )
}

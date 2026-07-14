import { ShieldCheck, UserRoundCog } from 'lucide-react'
import type { Actor, Role } from '../types/api'

interface IdentityBarProps {
  actor: Actor
  onChange: (actor: Actor) => void
}

const roleDefaults: Record<Role, string> = {
  researcher: 'xiaomei-researcher',
  reviewer: 'xiaomei-reviewer',
  admin: 'xiaomei-admin',
}

export function IdentityBar({ actor, onChange }: IdentityBarProps) {
  return (
    <section className="identity-bar" aria-label="Demonstration identity">
      <div className="identity-bar__copy">
        <UserRoundCog aria-hidden="true" />
        <div>
          <strong>Role-based demo session</strong>
          <span>Headers simulate identity locally; production would use managed identity.</span>
        </div>
      </div>
      <label>
        <span>User</span>
        <input
          value={actor.name}
          onChange={(event) => onChange({ ...actor, name: event.target.value })}
        />
      </label>
      <label>
        <span>Role</span>
        <select
          value={actor.role}
          onChange={(event) => {
            const role = event.target.value as Role
            onChange({ role, name: roleDefaults[role] })
          }}
        >
          <option value="researcher">Researcher</option>
          <option value="reviewer">Reviewer</option>
          <option value="admin">Admin</option>
        </select>
      </label>
      <span className="identity-pill"><ShieldCheck size={15} /> {actor.role}</span>
    </section>
  )
}

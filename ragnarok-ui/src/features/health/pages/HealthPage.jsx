import { useEffect, useState } from 'react'
import { getHealth } from '../../../api/endpoints/health'
import { ServiceStatusGrid } from '../components/ServiceStatusGrid'

export function HealthPage() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getHealth().then(setHealth).catch(setError)
  }, [])

  return (
    <section className="page">
      <h2 className="page-title">Health</h2>
      <div className="panel">
        {error && <p className="muted">Khong tai duoc health.</p>}
        {!error && <ServiceStatusGrid health={health} />}
      </div>
    </section>
  )
}

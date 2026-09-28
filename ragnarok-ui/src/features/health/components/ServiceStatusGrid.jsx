export function ServiceStatusGrid({ health }) {
  if (!health) {
    return <p className="muted">Chua co du lieu health.</p>
  }

  return (
    <dl>
      {Object.entries(health).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

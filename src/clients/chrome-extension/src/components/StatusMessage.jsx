import React, { useEffect } from 'react'

function StatusMessage({ message, type, onClose }) {
  useEffect(() => {
    if (message) {
      const timer = setTimeout(() => {
        onClose()
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [message, onClose])

  if (!message) return null

  return (
    <div className="status-message-container">
      <div className={`status-message status-${type}`}>
        {message}
      </div>
    </div>
  )
}

export default StatusMessage

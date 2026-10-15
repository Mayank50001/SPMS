import React from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { AppRoutes } from './routes'
import './App.css'

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App

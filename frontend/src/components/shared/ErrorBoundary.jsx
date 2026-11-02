import React from 'react';

export default class ErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('Nova UI error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="app-error" role="alert">
          <h1>Nova could not display this page.</h1>
          <p>Reload the page to reconnect to your store.</p>
          <button onClick={() => window.location.reload()}>Reload Nova</button>
        </main>
      );
    }
    return this.props.children;
  }
}

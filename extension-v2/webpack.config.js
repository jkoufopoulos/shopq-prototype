const path = require('path');

module.exports = {
  mode: 'production',
  entry: {
    capture: './src/capture.js'
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: '[name].bundle.js'
  },
  resolve: {
    extensions: ['.js']
  },
  optimization: {
    minimize: true
  }
};

const path = require('path');

module.exports = {
  mode: 'production',
  entry: {
    content: './src/content.js'
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

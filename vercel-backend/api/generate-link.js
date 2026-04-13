const { generateDeviceId, createShareLink } = require('./lib');

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }
  
  const { friendName } = req.body;
  if (!friendName) {
    return res.status(400).json({ error: 'friendName required' });
  }
  
  const deviceId = generateDeviceId();
  const shareLinkId = createShareLink(deviceId, friendName);
  
  const shareUrl = `${req.headers['x-forwarded-proto'] || 'https'}://${req.headers.host}/api/share/${shareLinkId}`;
  
  res.status(200).json({
    deviceId,
    shareLinkId,
    shareUrl,
    message: `Share this link with your friend: ${shareUrl}`
  });
}

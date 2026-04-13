const { getDevice, getDeviceByShareLink } = require('./lib');

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }
  
  const { id, type = 'device' } = req.query;
  
  if (!id) {
    return res.status(400).json({ error: 'id query parameter required' });
  }
  
  let device;
  
  if (type === 'sharelink') {
    device = getDeviceByShareLink(id);
  } else {
    device = getDevice(id);
  }
  
  if (!device) {
    return res.status(404).json({
      error: 'Device not found or expired',
      offline: true
    });
  }
  
  res.status(200).json({
    success: true,
    device: {
      deviceId: device.deviceId,
      publicIp: device.publicIp,
      localIp: device.localIp,
      friendName: device.friendName,
      expiresAt: device.expiresAt
    }
  });
}

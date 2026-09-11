using System.Net.Sockets;
using UnityEngine;

public class TcpTest : MonoBehaviour
{
    void Start()
    {
        try
        {
            using (var client = new TcpClient())
            {
                client.Connect("192.168.172.242", 4840);
                Debug.Log("TCP OK: " + client.Connected);
            }
        }
        catch (System.Exception e)
        {
            Debug.LogError("TCP FEILET: " + e);
        }
    }
}
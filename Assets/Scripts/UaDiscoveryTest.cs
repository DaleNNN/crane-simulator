using System;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using Opc.Ua;

public class UaDiscoveryTest : MonoBehaviour
{
    [SerializeField] private string serverUrl = "opc.tcp://192.168.172.242:4840";

    void Start()
    {
        Utils.SetTraceMask(Utils.TraceMasks.All);
        Utils.Tracing.TraceEventHandler += (s, e) =>
        {
            string msg;
            try
            {
                if (!string.IsNullOrEmpty(e.Format) && e.Arguments != null && e.Arguments.Length > 0)
                    msg = string.Format(e.Format, e.Arguments);
                else if (!string.IsNullOrEmpty(e.Format))
                    msg = e.Format;
                else
                    msg = e.Message ?? "(tom)";
            }
            catch { msg = e.Format ?? "(formateringsfeil)"; }

            Debug.Log("[UA] " + msg);
            if (e.Exception != null) Debug.LogError("[UA EX] " + e.Exception);
        };

        Debug.Log("Starter discovery PÅ BAKGRUNNSTRÅD...");

        Task.Run(() =>
        {
            SynchronizationContext.SetSynchronizationContext(null);
            Debug.Log("Tråd-ID: " + Thread.CurrentThread.ManagedThreadId);

            try
            {
                using (var dc = DiscoveryClient.Create(new Uri(serverUrl)))
                {
                    var endpoints = dc.GetEndpoints(null);
                    Debug.Log($"=== FANT {endpoints.Count} ENDPOINTS ===");
                    foreach (var ep in endpoints)
                    {
                        Debug.Log($"URL: {ep.EndpointUrl}");
                        Debug.Log($"   Mode: {ep.SecurityMode}  Policy: {ep.SecurityPolicyUri}");
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError("FEILET: " + e.Message);
            }
        });
    }
}